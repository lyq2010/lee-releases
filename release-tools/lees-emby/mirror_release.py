#!/usr/bin/env python3
"""Publish a Lee's Emby release mirror and verify metadata without downloading remote objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mirror_retention import cos_keys, prune_old_assets, r2_keys, r2_objects_path, version_tuple, old_assets


MANIFEST_NAME = "latest-lees-emby.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirror_metadata import verify_cos, verify_r2, r2_path


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def public_base(name: str) -> str:
    base = require_env(name).rstrip("/")
    if "://" not in base:
        base = f"https://{base}"
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit(f"{name} is invalid: {base}")
    return base


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def safe_asset_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or Path(value).name != value or "/" in value or "\\" in value:
        raise SystemExit(f"Manifest field {field} is not a safe asset name")
    return value


def load_release(assets: Path) -> tuple[dict[str, Any], Path, Path]:
    manifest_path = assets / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SystemExit(f"Missing release manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in ("sourceArchive", "sourceSha256", "sourceSize"):
        manifest.pop(field, None)
    package_name = safe_asset_name(manifest.get("package"), "package")
    version = str(manifest.get("version", ""))
    version_tuple(version)
    if package_name != f"LeesEmby_{version}_x64-setup.exe":
        raise SystemExit("Manifest version and asset names disagree")
    package_path = assets / package_name
    if not package_path.is_file():
        raise SystemExit("Lee's Emby release assets are incomplete")

    package_url_name = Path(urllib.parse.urlparse(str(manifest.get("url", ""))).path).name
    if package_url_name != package_name:
        raise SystemExit("Manifest package and URL disagree")
    if sha256(package_path) != str(manifest.get("sha256", "")).upper() or package_path.stat().st_size != manifest.get("size"):
        raise SystemExit("Lee's Emby package hash or size mismatch")
    if manifest.get("platform") != "windows-x86_64" or not manifest.get("certificateThumbprint"):
        raise SystemExit("Lee's Emby manifest identity fields are invalid")
    return manifest, manifest_path, package_path


def write_mirror_manifest(manifest: dict[str, Any], manifest_path: Path, base: str, package: Path) -> None:
    manifest["url"] = f"{base}/{package.name}"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reject_downgrade(keys, version, prefix=""):
    # Existing asset names provide version evidence without reading the remote feed.
    old_assets(keys, version, prefix)
    print("防降级已按对象列表核对；远端清单正文版本未验证。")


def mirror_cos(assets: Path) -> None:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as error:
        raise SystemExit("cos-python-sdk-v5 is required for the COS mirror") from error

    manifest, manifest_path, package = load_release(assets)
    base = public_base("COS_PUBLIC_BASE_URL")
    parsed = urllib.parse.urlparse(base)
    prefix = parsed.path.strip("/")
    object_key = lambda name: f"{prefix}/{name}" if prefix else name
    bucket = require_env("TENCENT_COS_BUCKET")
    client = CosS3Client(
        CosConfig(
            Region=require_env("TENCENT_COS_REGION"),
            SecretId=require_env("TENCENT_COS_SECRET_ID"),
            SecretKey=require_env("TENCENT_COS_SECRET_KEY"),
            Scheme="https",
            Timeout=60,
        )
    )

    reject_downgrade(cos_keys(client, bucket, prefix), manifest["version"], prefix)
    print(f"Uploading COS asset: {package.name} ({package.stat().st_size} bytes)", flush=True)
    client.upload_file(Bucket=bucket, LocalFilePath=str(package), Key=object_key(package.name), EnableMD5=False)
    print(f"Uploaded COS asset: {package.name}", flush=True)
    write_mirror_manifest(manifest, manifest_path, base, package)
    client.put_object(
        Bucket=bucket,
        Body=manifest_path.read_bytes(),
        Key=object_key(MANIFEST_NAME),
        ContentType="application/json; charset=utf-8",
    )
    verify_cos(client, bucket, {object_key(p.name): p.stat().st_size for p in (package, manifest_path)})
    prune_old_assets(
        lambda: cos_keys(client, bucket, prefix),
        lambda key: client.delete_object(Bucket=bucket, Key=key),
        manifest["version"], prefix,
    )
    verify_cos(client, bucket, {object_key(p.name): p.stat().st_size for p in (package, manifest_path)})

    print("COS Lee's Emby mirror complete")


def cloudflare_request(token: str, method: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"https://api.cloudflare.com/client/v4{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, method=method, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("success"):
        raise SystemExit(json.dumps(data, ensure_ascii=False))
    return data


def wrangler_put(bucket: str, object_name: str, source: Path, content_type: str | None, env: dict[str, str]) -> None:
    command = [
        "npm",
        "exec",
        "--yes",
        "--package",
        "wrangler@4",
        "--",
        "wrangler",
        "r2",
        "object",
        "put",
        f"{bucket}/{object_name}",
        "--file",
        str(source),
    ]
    if content_type:
        command.extend(("--content-type", content_type))
    command.append("--remote")
    subprocess.run(command, check=True, env=env)


def mirror_r2(assets: Path) -> None:
    manifest, manifest_path, package = load_release(assets)
    base = public_base("R2_PUBLIC_BASE_URL")
    bucket = require_env("R2_BUCKET")
    token = require_env("CLOUDFLARE_API_TOKEN")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not account_id:
        accounts = cloudflare_request(token, "GET", "/accounts").get("result") or []
        if not accounts:
            raise SystemExit("No Cloudflare account is available to the API token")
        account_id = accounts[0]["id"]

    command_env = os.environ.copy()
    command_env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    reject_downgrade(r2_keys(cloudflare_request, token, account_id, bucket), manifest["version"])
    wrangler_put(bucket, package.name, package, None, command_env)
    write_mirror_manifest(manifest, manifest_path, base, package)
    wrangler_put(bucket, MANIFEST_NAME, manifest_path, "application/json; charset=utf-8", command_env)
    verify_r2(lambda method, path, params=None: cloudflare_request(token, method, path, params),
              r2_path(account_id, bucket), {p.name: p.stat().st_size for p in (package, manifest_path)})
    prune_old_assets(
        lambda: r2_keys(cloudflare_request, token, account_id, bucket),
        lambda key: cloudflare_request(token, "DELETE", f"{r2_objects_path(account_id, bucket)}/{urllib.parse.quote(key, safe='/')}"),
        manifest["version"],
    )
    verify_r2(lambda method, path, params=None: cloudflare_request(token, method, path, params),
              r2_path(account_id, bucket), {p.name: p.stat().st_size for p in (package, manifest_path)})

    print("R2 Lee's Emby mirror complete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=("cos", "r2"))
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    args = parser.parse_args()
    if args.provider == "cos":
        mirror_cos(args.assets)
    else:
        mirror_r2(args.assets)


if __name__ == "__main__":
    main()
