"""Publish Music mirrors using local integrity checks and remote metadata only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirror_metadata import r2_objects, r2_path, verify_cos, verify_r2

# Keep the source repository's existing product-scoped retention rules.
sys.path.insert(0, str(Path("tools/release").resolve()))
from prune import cloudflare_request, prune_cos, prune_r2

MANIFEST = "latest-lees-music.json"
ASSET = re.compile(r"lees-music-(\d+)\.(\d+)\.(\d+)(?:\.apk|-source\.zip|-SHA256SUMS\.txt)")


def digest(path, algorithm="sha256"):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, algorithm).hexdigest()


def load_release(assets):
    manifest = json.loads((assets / MANIFEST).read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Invalid Music version")
    apk = assets / f"lees-music-{version}.apk"
    checksum = assets / f"lees-music-{version}-SHA256SUMS.txt"
    if manifest["apk"] != apk.name or apk.stat().st_size != manifest["size"] or digest(apk) != manifest["sha256"]:
        raise SystemExit("Local APK integrity mismatch")
    expected = {apk.name, checksum.name, MANIFEST}
    if {p.name for p in assets.iterdir() if p.is_file()} != expected:
        raise SystemExit("Unexpected or incomplete Music assets")
    entries = checksum.read_text().splitlines()
    if entries != [f"{manifest['sha256']}  {apk.name}"]:
        raise SystemExit("Local Music checksum mismatch")
    return manifest, [apk, checksum], {p.name: p for p in (apk, checksum, assets / MANIFEST)}


def reject_replacement(objects, version, files):
    current = tuple(map(int, version.split(".")))
    same_version = False
    for key in objects:
        match = ASSET.fullmatch(key)
        if match:
            existing = tuple(map(int, match.groups()))
            if existing > current:
                raise SystemExit("Refusing to replace a newer Music mirror release")
            same_version |= existing == current
    if same_version:
        # Only a single-part MD5 ETag can establish same-version identity here.
        # Opaque/multipart ETags fail closed; never download to resolve uncertainty.
        for name, path in files.items():
            if name in objects and str(objects[name].get("etag", "")).strip('"').lower() != digest(path, "md5"):
                raise SystemExit(f"Same-version identity unverified from metadata: {name}; refusing replacement")
    print("防降级已按对象列表核对；远端清单正文和 versionCode 未验证。")


def cos_objects(client, bucket):
    objects, marker, seen = {}, "", set()
    while True:
        page = client.list_objects(Bucket=bucket, Prefix="lees-music-", Marker=marker, MaxKeys=1000)
        objects.update({item["Key"]: {"etag": item.get("ETag", "")} for item in page.get("Contents") or []})
        if page.get("IsTruncated") not in (True, "true"):
            return objects
        marker = page.get("NextMarker")
        if not marker or marker in seen:
            raise SystemExit("Invalid COS pagination")
        seen.add(marker)


def main(provider):
    assets = Path("assets")
    manifest, files, paths = load_release(assets)
    sizes = {name: path.stat().st_size for name, path in paths.items()}
    if provider == "cos":
        from qcloud_cos import CosConfig, CosS3Client
        from qcloud_cos.cos_exception import CosServiceError
        client = CosS3Client(CosConfig(Region=os.environ["TENCENT_COS_REGION"],
            SecretId=os.environ["TENCENT_COS_SECRET_ID"], SecretKey=os.environ["TENCENT_COS_SECRET_KEY"], Scheme="https"))
        bucket = os.environ["TENCENT_COS_BUCKET"]
        objects = cos_objects(client, bucket)
        try:
            head = client.head_object(Bucket=bucket, Key=MANIFEST)
            objects[MANIFEST] = {"etag": head.get("ETag", "")}
        except CosServiceError as error:
            if str(error.get_status_code()) != "404":
                raise
        reject_replacement(objects, manifest["version"], paths)

        def upload(path):
            with path.open("rb") as body:
                client.put_object(Bucket=bucket, Body=body, Key=path.name,
                    CacheControl="no-cache" if path.suffix == ".json" else "public, max-age=31536000, immutable")

        verify = lambda expected: verify_cos(client, bucket, expected)
        prune = lambda: prune_cos(client, bucket, manifest["version"])
    elif provider == "r2":
        token = os.environ["CLOUDFLARE_API_TOKEN"]
        request = lambda method, path, params=None: cloudflare_request(token, method, path, params)
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if not account:
            accounts = request("GET", "/accounts").get("result") or []
            if len(accounts) != 1:
                raise SystemExit("Set CLOUDFLARE_ACCOUNT_ID explicitly; account is ambiguous")
            account = accounts[0]["id"]
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = account
        bucket_path = r2_path(account, "packing-list-releases")
        objects = r2_objects(request, bucket_path, "lees-music-")
        objects.update(r2_objects(request, bucket_path, MANIFEST))
        reject_replacement(objects, manifest["version"], paths)

        def upload(path):
            subprocess.run(["npx", "--yes", "wrangler@4", "r2", "object", "put",
                f"packing-list-releases/{path.name}", "--file", str(path), "--remote",
                "--content-type", "application/json" if path.suffix == ".json" else "application/octet-stream"], check=True)

        verify = lambda expected: verify_r2(request, bucket_path, expected)
        prune = lambda: prune_r2(request, bucket_path, manifest["version"])
    else:
        raise SystemExit("Expected cos or r2")
    for path in files:
        upload(path)
    verify({path.name: sizes[path.name] for path in files})
    upload(paths[MANIFEST])
    verify(sizes)
    prune()
    print(f"Music {provider} mirror metadata verified: {manifest['version']}")


if __name__ == "__main__":
    main(sys.argv[1])
