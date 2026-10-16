"""Stage immutable releases, then verify both mirrors before promotion and scoped cleanup."""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from retention import prune

SCRIPT = Path(__file__).parent
SOURCES = ('cos', 'r2')


def verified_manifest(file=None, *, raw=None):
    return json.loads(subprocess.check_output(
        ['node', str(SCRIPT / 'verify.mjs'), '-' if raw is not None else str(file)],
        input=raw, encoding='utf-8'))


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


def public_identity(url):
    # HEAD only: never read object bodies, even partially or into memory.
    request = urllib.request.Request(url, method='HEAD', headers={
        'User-Agent': 'Mozilla/5.0 LeesPDF-Release/1', 'Cache-Control': 'no-cache',
        'Accept-Encoding': 'identity'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            etag = response.headers.get('ETag', '').strip('"').lower()
            length = response.headers.get('Content-Length', '')
            if not re.fullmatch(r'[0-9a-f]{32}', etag) or not re.fullmatch(r'[0-9]+', length):
                raise RuntimeError('Mirror HEAD metadata is insufficient; body download is forbidden')
            size = int(length)
            if size > 768 * 1024 * 1024:
                raise RuntimeError('Mirror object exceeds budget')
            return etag, size
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 404:
            return None
        raise


def identity(data):
    # Single-part ETag/MD5 is transport metadata, not a remote SHA-256 verification.
    return hashlib.md5(data, usedforsecurity=False).hexdigest(), len(data)


def file_identity(file):
    digest, size = hashlib.md5(usedforsecurity=False), 0
    with file.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def manifest_metadata(outer, payload, source):
    metadata = dict(outer)
    metadata['platforms'] = {
        target: {'url': urllib.parse.urljoin(base(source), value['updaterArtifact']['path']),
                 'signature': value['updaterArtifact']['signature']}
        for target, value in payload['platforms'].items()}
    return (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def github_previous_manifest():
    # The signed prior release comes from GitHub, never from a bucket object GET.
    rows = json.loads(subprocess.check_output([
        'gh', 'release', 'list', '--repo', 'lyq2010/lee-releases', '--exclude-drafts',
        '--exclude-pre-releases', '--limit', '100', '--json', 'tagName'], encoding='utf-8'))
    tags = [row['tagName'] for row in rows if re.fullmatch(r'lees-pdf-v[0-9]+\.[0-9]+\.[0-9]+', row['tagName'])]
    if not tags:
        return None
    tag = max(tags, key=lambda value: tuple(map(int, value.removeprefix('lees-pdf-v').split('.'))))
    raw = subprocess.check_output([
        'gh', 'release', 'download', tag, '--repo', 'lyq2010/lee-releases',
        '--pattern', 'release-manifest.json', '--output', '-'], encoding='utf-8')
    if len(raw.encode('utf-8')) > 65536:
        raise RuntimeError('GitHub release manifest exceeds budget')
    verified = verified_manifest(raw=raw)
    if verified['payload']['releaseId'] != tag or tag != 'lees-pdf-v' + verified['payload']['version']:
        raise RuntimeError('Prior GitHub release identity mismatch')
    return json.loads(raw), verified


def put(source, key, file, mutable=False):
    expected = file_identity(file)
    url = urllib.parse.urljoin(base(source), key)
    existing = public_identity(url)
    if existing == expected:
        return
    if existing is not None and not mutable:
        raise RuntimeError('Immutable release object already differs')
    if source == 'cos':
        from qcloud_cos import CosConfig, CosS3Client
        client = CosS3Client(CosConfig(Region=env('TENCENT_COS_REGION'), SecretId=env('TENCENT_COS_SECRET_ID'), SecretKey=env('TENCENT_COS_SECRET_KEY'), Scheme='https'))
        path_prefix = urllib.parse.urlsplit(base(source)).path.strip('/')
        object_key = f'{path_prefix}/{key}' if path_prefix else key
        # Use a single PUT with Content-MD5 so HEAD ETag can be compared without a download.
        with file.open('rb') as body:
            client.put_object(Bucket=env('TENCENT_COS_BUCKET'), Body=body, Key=object_key,
                              ContentLength=expected[1], ContentMD5=base64.b64encode(bytes.fromhex(expected[0])).decode('ascii'),
                              CacheControl='no-cache' if mutable else 'public, max-age=31536000, immutable')
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
    if public_identity(url) != expected:
        raise RuntimeError('Public mirror HEAD metadata does not match')


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
        self.expected = {key: file_identity(file) for key, file in self.files.items()}

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
        return manifest_metadata(self.outer, self.payload, source)

    def readiness(self, source):
        (self.root / f'readiness-{source}.json').write_text(json.dumps({
            'source': source, 'verified': True, 'version': self.version,
            'payloadSha256': self.verified['payloadSha256'], 'runId': env('GITHUB_RUN_ID'),
            'verification': 'head-metadata-only'}), encoding='utf-8')

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
        digest = identity(expected)
        for key in ([self.prefix + 'release-manifest.json', 'latest-lees-pdf.json'] if pointers
                    else [self.prefix + 'release-manifest.json']):
            if public_identity(urllib.parse.urljoin(base(source), key)) != digest:
                raise RuntimeError('Mirror manifest does not match signed release')
        if assets:
            for key, expected in self.expected.items():
                actual = public_identity(urllib.parse.urljoin(base(source), key))
                if actual != expected:
                    raise RuntimeError(f'Current asset missing or changed: {source} {key}; expected={expected}, actual={actual}')

    def verify_both(self, pointers=False, assets=True):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda source: self.verify_source(source, pointers, assets), SOURCES))

    def check_previous(self):
        previous = github_previous_manifest()
        if previous:
            outer, verified = previous
            old_version = tuple(map(int, verified['payload']['version'].split('.')))
            new_version = tuple(map(int, self.version.split('.')))
            if old_version > new_version or (old_version == new_version and verified['payloadSha256'] != self.verified['payloadSha256']):
                raise RuntimeError('Refusing a downgrade or conflicting release version')
        for source in SOURCES:
            actual = public_identity(urllib.parse.urljoin(base(source), 'latest-lees-pdf.json'))
            if actual is None or actual == identity(self.metadata(source)):
                continue
            if previous and actual == identity(manifest_metadata(outer, verified['payload'], source)):
                continue
            raise RuntimeError('Existing pointer does not match a signed GitHub release; download refused')

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
