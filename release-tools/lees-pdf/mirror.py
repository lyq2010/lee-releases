"""Stage immutable releases, then verify both mirrors before promotion and scoped cleanup."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from retention import prune

SCRIPT = Path(__file__).parent
SOURCES = ('cos', 'r2')


def verified_manifest(file):
    return json.loads(subprocess.check_output(['node', str(SCRIPT / 'verify.mjs'), str(file)], encoding='utf-8'))


def env(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing {name}')
    return value


def base(source):
    value = env('COS_PUBLIC_BASE_URL') if source == 'cos' else 'https://plt-releases.leenbsl.workers.dev/'
    if '://' not in value:
        value = 'https://' + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise RuntimeError('Invalid mirror base')
    return value.rstrip('/') + '/'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Redirect refused')


def public_digest(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 LeesPDF-Release/1', 'Cache-Control': 'no-cache'})
    digest, size = hashlib.sha256(), 0
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > 768 * 1024 * 1024:
                    raise RuntimeError('Mirror object exceeds budget')
                digest.update(block)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return digest.hexdigest(), size


def put(source, key, file, mutable=False):
    expected = (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_size)
    url = urllib.parse.urljoin(base(source), key)
    existing = public_digest(url)
    if existing == expected:
        return
    if existing is not None and not mutable:
        raise RuntimeError('Immutable release object already differs')
    if source == 'cos':
        from qcloud_cos import CosConfig, CosS3Client
        client = CosS3Client(CosConfig(Region=env('TENCENT_COS_REGION'), SecretId=env('TENCENT_COS_SECRET_ID'), SecretKey=env('TENCENT_COS_SECRET_KEY'), Scheme='https'))
        path_prefix = urllib.parse.urlsplit(base(source)).path.strip('/')
        object_key = f'{path_prefix}/{key}' if path_prefix else key
        client.upload_file(Bucket=env('TENCENT_COS_BUCKET'), LocalFilePath=str(file), Key=object_key, EnableMD5=True, CacheControl='no-cache' if mutable else 'public, max-age=31536000, immutable')
    else:
        command_env = os.environ.copy()
        command_env['CLOUDFLARE_API_TOKEN'] = env('CF_API_TOKEN')
        account = os.environ.get('CF_ACCOUNT_ID')
        if not account:
            request = urllib.request.Request('https://api.cloudflare.com/client/v4/accounts', headers={'Authorization': 'Bearer ' + env('CF_API_TOKEN')})
            with urllib.request.urlopen(request, timeout=30) as response:
                accounts = json.load(response)
            if not accounts.get('success') or len(accounts.get('result', [])) != 1:
                raise RuntimeError('Set CF_ACCOUNT_ID to choose an explicit account')
            account = accounts['result'][0]['id']
        command_env['CLOUDFLARE_ACCOUNT_ID'] = account
        subprocess.run(['node', env('LEESPDF_WRANGLER_CLI'), 'r2', 'object', 'put', f'{env("R2_BUCKET")}/{key}', '--file', str(file), '--remote', '--cache-control', 'no-cache' if mutable else 'public, max-age=31536000, immutable'], env=command_env, check=True)
    if public_digest(url) != expected:
        raise RuntimeError('Public mirror readback does not match')


class Release:
    def __init__(self, root):
        self.root = root
        self.verified = verified_manifest(root / 'release-manifest.json')
        self.payload = self.verified['payload']
        self.version = self.payload['version']
        if self.payload['releaseId'] != env('PUBLIC_TAG') or env('PUBLIC_TAG') != f'lees-pdf-v{self.version}':
            raise RuntimeError('Draft tag does not match signed release identity')
        self.prefix = f'lees-pdf/releases/{self.version}/'
        self.outer = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))
        self.files = self.artifacts()
        self.expected = {key: (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_size)
                         for key, file in self.files.items()}

    def artifacts(self):
        result = {}
        for platform in self.payload['platforms'].values():
            for key in ('updaterArtifact', 'installerArtifact'):
                item = platform[key]
                path = item['path']
                if not path.startswith(self.prefix) or Path(path).name != path[len(self.prefix):] or '..' in path or '\\' in path:
                    raise RuntimeError('Unsafe asset path')
                file = self.root / Path(path).name
                if file.stat().st_size != item['size'] or hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']:
                    raise RuntimeError('Signed artifact mismatch')
                result[path] = file
        for line in (self.root / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
            digest, name = line.split('  ', 1)
            if Path(name).name != name or not name.startswith('lees-pdf-'):
                raise RuntimeError('Unsafe public material name')
            file = self.root / name
            if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Material checksum mismatch')
            result[self.prefix + name] = file
        result[self.prefix + 'SHA256SUMS'] = self.root / 'SHA256SUMS'
        return result

    def metadata(self, source):
        metadata = dict(self.outer)
        metadata['platforms'] = {
            target: {'url': urllib.parse.urljoin(base(source), value['updaterArtifact']['path']),
                     'signature': value['updaterArtifact']['signature']}
            for target, value in self.payload['platforms'].items()}
        return (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')

    def readiness(self, source):
        (self.root / f'readiness-{source}.json').write_text(json.dumps({
            'source': source, 'verified': True, 'version': self.version,
            'payloadSha256': self.verified['payloadSha256'], 'runId': env('GITHUB_RUN_ID')}), encoding='utf-8')

    def stage(self, source):
        if source not in SOURCES:
            raise RuntimeError('Invalid mirror source')
        for key, file in self.files.items():
            put(source, key, file)
        local = self.root / f'manifest-{source}.json'
        local.write_bytes(self.metadata(source))
        put(source, self.prefix + 'release-manifest.json', local)
        self.readiness(source)

    def verify_source(self, source, pointers=False, assets=True):
        expected = self.metadata(source)
        digest = (hashlib.sha256(expected).hexdigest(), len(expected))
        for key in ([self.prefix + 'release-manifest.json', 'latest-lees-pdf.json'] if pointers
                    else [self.prefix + 'release-manifest.json']):
            if public_digest(urllib.parse.urljoin(base(source), key)) != digest:
                raise RuntimeError('Mirror manifest does not match signed release')
        if assets:
            for key, expected in self.expected.items():
                actual = public_digest(urllib.parse.urljoin(base(source), key))
                if actual != expected:
                    raise RuntimeError(f'Current asset missing or changed: {source} {key}; expected={expected}, actual={actual}')

    def verify_both(self, pointers=False, assets=True):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda source: self.verify_source(source, pointers, assets), SOURCES))

    def check_previous(self):
        for source in SOURCES:
            request = urllib.request.Request(urllib.parse.urljoin(base(source), 'latest-lees-pdf.json'),
                                            headers={'User-Agent': 'Mozilla/5.0 LeesPDF-Release/1', 'Cache-Control': 'no-cache'})
            try:
                with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                    previous = response.read(65537)
                if len(previous) > 65536:
                    raise RuntimeError('Existing latest manifest exceeds budget')
                prior_file = self.root / f'previous-latest-{source}.json'
                prior_file.write_bytes(previous)
                prior = verified_manifest(prior_file)
                old_version = tuple(map(int, prior['payload']['version'].split('.')))
                new_version = tuple(map(int, self.version.split('.')))
                if old_version > new_version or (old_version == new_version and prior['payloadSha256'] != self.verified['payloadSha256']):
                    raise RuntimeError('Refusing a downgrade or conflicting release version')
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise

    def cleanup(self, assets_verified=False):
        # publish() just verified every immutable asset in this process. Check both pointers again before pruning.
        self.verify_both(pointers=True, assets=not assets_verified)
        prune(self.version, base('cos'))
        self.verify_both(pointers=True)

    def publish(self):
        self.verify_both()
        for source in SOURCES:
            self.readiness(source)
        subprocess.run(['node', str(SCRIPT / 'barrier.mjs'), str(self.root)], check=True)
        self.check_previous()
        for source in SOURCES:
            local = self.root / f'manifest-{source}.json'
            local.write_bytes(self.metadata(source))
            put(source, 'latest-lees-pdf.json', local, mutable=True)
        self.cleanup(assets_verified=True)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode not in ('stage', 'release', 'cleanup'):
        raise RuntimeError('Invalid mirror mode')
    release = Release(Path(sys.argv[2]))
    if mode == 'stage':
        release.stage(env('MIRROR'))
    elif mode == 'release':
        release.publish()
    else:
        release.cleanup()
