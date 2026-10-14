"""Keep only the latest PDF version in COS and R2, scoped to PDF release keys."""
import json
import os
import re
import urllib.parse
import urllib.request


def old_assets(keys, version, prefix=''):
    current = tuple(map(int, version.split('.')))
    root = prefix.strip('/')
    root = (root + '/' if root else '') + 'lees-pdf/releases/'
    old = []
    pattern = re.compile(r'(\d+\.\d+\.\d+)/(lees-pdf-[\w.-]+|release-manifest\.json|SHA256SUMS)')
    for key in keys:
        if not key.startswith(root):
            continue
        match = pattern.fullmatch(key[len(root):])
        if not match:
            raise RuntimeError('Unexpected PDF release key; refuse cleanup')
        asset_version = tuple(map(int, match[1].split('.')))
        if asset_version > current:
            raise RuntimeError('Mirror contains a newer release; refuse cleanup')
        if asset_version < current:
            old.append(key)
    return sorted(set(old))


def api(method, path, params=None):
    url = 'https://api.cloudflare.com/client/v4' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, method=method, headers={'Authorization': 'Bearer ' + os.environ['CF_API_TOKEN']})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if not data.get('success'):
        raise RuntimeError('R2 API operation failed')
    return data


def cos_keys(client, bucket, prefix):
    keys, marker = [], ''
    while True:
        page = client.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        keys.extend(item['Key'] for item in page.get('Contents', []))
        if str(page.get('IsTruncated', 'false')).lower() != 'true':
            return keys
        next_marker = page.get('NextMarker')
        if not next_marker or next_marker == marker:
            raise RuntimeError('Invalid COS pagination')
        marker = next_marker


def r2_keys(path):
    keys, params = [], {'prefix': 'lees-pdf/releases/', 'per_page': 1000}
    while True:
        page = api('GET', path, params)
        keys.extend(item['key'] for item in page.get('result', []))
        info = page.get('result_info') or {}
        if not info.get('is_truncated'):
            return keys
        cursor = info.get('cursor')
        if not cursor or cursor == params.get('cursor'):
            raise RuntimeError('Invalid R2 pagination')
        params['cursor'] = cursor


def prune(version, cos_base):
    from qcloud_cos import CosConfig, CosS3Client
    client = CosS3Client(CosConfig(Region=os.environ['TENCENT_COS_REGION'], SecretId=os.environ['TENCENT_COS_SECRET_ID'], SecretKey=os.environ['TENCENT_COS_SECRET_KEY'], Scheme='https'))
    bucket = os.environ['TENCENT_COS_BUCKET']
    prefix = urllib.parse.urlsplit(cos_base).path.strip('/')
    root = (prefix + '/' if prefix else '') + 'lees-pdf/releases/'
    cos_old = old_assets(cos_keys(client, bucket, root), version, prefix)
    account = os.environ.get('CF_ACCOUNT_ID')
    if not account:
        accounts = api('GET', '/accounts')['result']
        if len(accounts) != 1:
            raise RuntimeError('Choose CF_ACCOUNT_ID explicitly')
        account = accounts[0]['id']
    path = f'/accounts/{urllib.parse.quote(account, safe="")}/r2/buckets/{urllib.parse.quote(os.environ["R2_BUCKET"], safe="")}/objects'
    r2_old = old_assets(r2_keys(path), version)
    # Enumerate and validate both complete plans before deleting either source.
    for key in cos_old:
        client.delete_object(Bucket=bucket, Key=key)
    for key in r2_old:
        api('DELETE', path + '/' + urllib.parse.quote(key, safe=''))
    if old_assets(cos_keys(client, bucket, root), version, prefix) or old_assets(r2_keys(path), version):
        raise RuntimeError('Old PDF versions remain after cleanup')
    print(f'PDF latest-only retention verified: {version}; COS {len(cos_old)}, R2 {len(r2_old)} old objects removed')
