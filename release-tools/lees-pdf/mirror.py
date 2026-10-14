"""Mirror signed PDF releases. Current immutable objects are never overwritten; old releases are pruned after promotion."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(sys.argv[2])
MODE = sys.argv[1]
SCRIPT = Path(__file__).parent
verified = json.loads(subprocess.check_output(['node', str(SCRIPT / 'verify.mjs'), str(ROOT / 'release-manifest.json')]))
payload = verified['payload']
version = payload['version']
if payload['releaseId'] != os.environ.get('PUBLIC_TAG') or payload['releaseId'] != f'lees-pdf-v{version}':
    raise RuntimeError('Draft tag does not match signed release identity')
prefix = f'lees-pdf/releases/{version}/'
outer = json.loads((ROOT / 'release-manifest.json').read_text())


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
        subprocess.run(['npm', 'exec', '--yes', '--package', 'wrangler@4', '--', 'wrangler', 'r2', 'object', 'put', f'{env("R2_BUCKET")}/{key}', '--file', str(file), '--remote', '--cache-control', 'no-cache' if mutable else 'public, max-age=31536000, immutable'], env=command_env, check=True)
    if public_digest(url) != expected:
        raise RuntimeError('Public mirror readback does not match')


def artifacts():
    result = {}
    for platform in payload['platforms'].values():
        for key in ('updaterArtifact', 'installerArtifact'):
            item = platform[key]
            path = item['path']
            if not path.startswith(prefix) or Path(path).name != path[len(prefix):] or '..' in path or '\\' in path:
                raise RuntimeError('Unsafe asset path')
            file = ROOT / Path(path).name
            if file.stat().st_size != item['size'] or hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Signed artifact mismatch')
            result[path] = file
    # Ancillary materials are covered by SHA256SUMS; only expected public filenames are accepted.
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if Path(name).name != name or not name.startswith('lees-pdf-'):
            raise RuntimeError('Unsafe public material name')
        file = ROOT / name
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Material checksum mismatch')
        result[prefix + name] = file
    result[prefix + 'SHA256SUMS'] = ROOT / 'SHA256SUMS'
    return result


files = artifacts()
if MODE == 'cleanup':
    from retention import prune

    def verify_current():
        for source in ('cos', 'r2'):
            metadata = dict(outer)
            metadata['platforms'] = {target: {'url': urllib.parse.urljoin(base(source), value['updaterArtifact']['path']), 'signature': value['updaterArtifact']['signature']} for target, value in payload['platforms'].items()}
            expected = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            for key in ('latest-lees-pdf.json', prefix + 'release-manifest.json'):
                if public_digest(urllib.parse.urljoin(base(source), key)) != (hashlib.sha256(expected).hexdigest(), len(expected)):
                    raise RuntimeError('Both promoted pointers must match before pruning')
            for key, file in files.items():
                if public_digest(urllib.parse.urljoin(base(source), key)) != (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_size):
                    raise RuntimeError('Current asset missing: pruning refused')

    verify_current()
    prune(version, base('cos'))
    verify_current()
    sys.exit(0)
for source in ([env('MIRROR')] if MODE == 'stage' else ['cos', 'r2']):
    if source not in ('cos', 'r2') or MODE not in ('stage', 'promote'):
        raise RuntimeError('Invalid mode/source')
    metadata = dict(outer)
    metadata['platforms'] = {target: {'url': urllib.parse.urljoin(base(source), value['updaterArtifact']['path']), 'signature': value['updaterArtifact']['signature']} for target, value in payload['platforms'].items()}
    local = ROOT / f'manifest-{source}.json'
    local.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for key, file in files.items():
        if MODE == 'stage':
            put(source, key, file)
        elif public_digest(urllib.parse.urljoin(base(source), key)) != (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_size):
            raise RuntimeError('Promotion requires all immutable assets to match')
    put(source, prefix + 'release-manifest.json', local)
    if MODE == 'stage':
        (ROOT / f'readiness-{source}.json').write_text(json.dumps({'source': source, 'verified': True, 'version': version, 'payloadSha256': verified['payloadSha256'], 'runId': env('GITHUB_RUN_ID')}))
# Both sources passed again before either mutable pointer is touched.
if MODE == 'promote':
    for source in ('cos', 'r2'):
        request = urllib.request.Request(urllib.parse.urljoin(base(source), 'latest-lees-pdf.json'), headers={'User-Agent': 'Mozilla/5.0 LeesPDF-Release/1', 'Cache-Control': 'no-cache'})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                previous = response.read(65537)
            if len(previous) > 65536:
                raise RuntimeError('Existing latest manifest exceeds budget')
            prior_file = ROOT / f'previous-latest-{source}.json'
            prior_file.write_bytes(previous)
            prior = json.loads(subprocess.check_output(['node', str(Path(__file__).with_name('verify.mjs')), str(prior_file)], text=True))
            old_version = tuple(map(int, prior['payload']['version'].split('.')))
            new_version = tuple(map(int, version.split('.')))
            if old_version > new_version or (old_version == new_version and prior['payloadSha256'] != verified['payloadSha256']):
                raise RuntimeError('Refusing a downgrade or conflicting release version')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    for source in ('cos', 'r2'):
        put(source, 'latest-lees-pdf.json', ROOT / f'manifest-{source}.json', mutable=True)
