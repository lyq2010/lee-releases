#!/usr/bin/env python3
"""Publish a Lee's Emby release mirror and verify its public update feed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mirror_retention import cos_keys, prune_old_assets, r2_keys, r2_objects_path, version_tuple


MANIFEST_NAME = "latest-lees-emby.json"
PUBLIC_FIELDS = (
    "version",
    "platform",
    "package",
    "url",
    "sha256",
    "size",
    "certificateThumbprint",
    "sourceArchive",
    "sourceSha256",
    "sourceSize",
    "signature",
)
# Cloudflare Bot Fight Mode rejects Python's default urllib User-Agent with 403.
VERIFY_USER_AGENT = "Mozilla/5.0 (compatible; LeesEmbyReleaseVerify/1.0)"
VERIFY_ATTEMPTS = 5
VERIFY_RETRY_DELAY_SECONDS = 2.0


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


def load_release(assets: Path) -> tuple[dict[str, Any], Path, Path, Path]:
    manifest_path = assets / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SystemExit(f"Missing release manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    package_name = safe_asset_name(manifest.get("package"), "package")
    source_name = safe_asset_name(manifest.get("sourceArchive"), "sourceArchive")
    version = str(manifest.get("version", ""))
    version_tuple(version)
    if package_name != f"LeesEmby_{version}_x64-setup.exe" or source_name != f"lees-emby_{version}_source.zip":
        raise SystemExit("Manifest version and asset names disagree")
    package_path = assets / package_name
    source_path = assets / source_name
    if not package_path.is_file() or not source_path.is_file():
        raise SystemExit("Lee's Emby release assets are incomplete")

    source_url_name = Path(urllib.parse.urlparse(str(manifest.get("url", ""))).path).name
    if source_url_name != package_name:
        raise SystemExit("Manifest package and URL disagree")
    if sha256(package_path) != str(manifest.get("sha256", "")).upper() or package_path.stat().st_size != manifest.get("size"):
        raise SystemExit("Lee's Emby package hash or size mismatch")
    if sha256(source_path) != str(manifest.get("sourceSha256", "")).upper() or source_path.stat().st_size != manifest.get("sourceSize"):
        raise SystemExit("Lee's Emby source archive hash or size mismatch")
    if manifest.get("platform") != "windows-x86_64" or not manifest.get("certificateThumbprint"):
        raise SystemExit("Lee's Emby manifest identity fields are invalid")
    return manifest, manifest_path, package_path, source_path


def write_mirror_manifest(manifest: dict[str, Any], manifest_path: Path, base: str, package: Path) -> None:
    manifest["url"] = f"{base}/{package.name}"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def open_public(url: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": VERIFY_USER_AGENT,
            "Cache-Control": "no-cache",
        },
    )
    return urllib.request.urlopen(request, timeout=30)


def reject_downgrade(base: str, version: str) -> None:
    run_id = urllib.parse.quote(os.environ.get("GITHUB_RUN_ID", "manual"), safe="")
    try:
        with open_public(f"{base}/{MANIFEST_NAME}?verify={run_id}") as response:
            published = json.loads(response.read().decode("utf-8"))
        if version_tuple(published["version"]) > version_tuple(version):
            raise SystemExit("Refusing to replace a newer Lee's Emby mirror release")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise


def verify_public(base: str, expected: dict[str, Any], package: Path, source: Path) -> None:
    run_id = urllib.parse.quote(os.environ.get("GITHUB_RUN_ID", "manual"), safe="")
    manifest_url = f"{base}/{MANIFEST_NAME}?verify={run_id}"
    last_error: Exception | None = None

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        try:
            with open_public(manifest_url) as response:
                published = json.loads(response.read().decode("utf-8"))
            mismatches = [field for field in PUBLIC_FIELDS if published.get(field) != expected.get(field)]
            if mismatches:
                raise SystemExit(f"Published Lee's Emby manifest mismatch: {', '.join(mismatches)}")

            for asset in (package, source):
                with open_public(f"{base}/{asset.name}?verify={run_id}", method="HEAD") as response:
                    if response.status != 200:
                        raise SystemExit(f"Lee's Emby mirror asset is not publicly available: {asset.name}")
            return
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {403, 404, 429, 500, 502, 503, 504} or attempt >= VERIFY_ATTEMPTS:
                raise
            print(
                f"Public mirror verify attempt {attempt}/{VERIFY_ATTEMPTS} got HTTP {error.code}; "
                f"retrying in {VERIFY_RETRY_DELAY_SECONDS:.0f}s"
            )
            time.sleep(VERIFY_RETRY_DELAY_SECONDS)
        except TimeoutError as error:
            last_error = error
            if attempt >= VERIFY_ATTEMPTS:
                raise
            print(
                f"Public mirror verify attempt {attempt}/{VERIFY_ATTEMPTS} timed out; "
                f"retrying in {VERIFY_RETRY_DELAY_SECONDS:.0f}s"
            )
            time.sleep(VERIFY_RETRY_DELAY_SECONDS)

    raise SystemExit(f"Public mirror verify failed after {VERIFY_ATTEMPTS} attempts: {last_error}")


def mirror_cos(assets: Path) -> None:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as error:
        raise SystemExit("cos-python-sdk-v5 is required for the COS mirror") from error

    manifest, manifest_path, package, source = load_release(assets)
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

    reject_downgrade(base, manifest["version"])
    for asset in (package, source):
        print(f"Uploading COS asset: {asset.name} ({asset.stat().st_size} bytes)", flush=True)
        client.upload_file(Bucket=bucket, LocalFilePath=str(asset), Key=object_key(asset.name), EnableMD5=False)
        print(f"Uploaded COS asset: {asset.name}", flush=True)
    write_mirror_manifest(manifest, manifest_path, base, package)
    client.put_object(
        Bucket=bucket,
        Body=manifest_path.read_bytes(),
        Key=object_key(MANIFEST_NAME),
        ContentType="application/json; charset=utf-8",
    )
    verify_public(base, manifest, package, source)
    prune_old_assets(
        lambda: cos_keys(client, bucket, prefix),
        lambda key: client.delete_object(Bucket=bucket, Key=key),
        manifest["version"], prefix,
    )
    verify_public(base, manifest, package, source)

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
    manifest, manifest_path, package, source = load_release(assets)
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
    reject_downgrade(base, manifest["version"])
    wrangler_put(bucket, package.name, package, None, command_env)
    wrangler_put(bucket, source.name, source, None, command_env)
    write_mirror_manifest(manifest, manifest_path, base, package)
    wrangler_put(bucket, MANIFEST_NAME, manifest_path, "application/json; charset=utf-8", command_env)
    verify_public(base, manifest, package, source)
    prune_old_assets(
        lambda: r2_keys(cloudflare_request, token, account_id, bucket),
        lambda key: cloudflare_request(token, "DELETE", f"{r2_objects_path(account_id, bucket)}/{urllib.parse.quote(key, safe='/')}"),
        manifest["version"],
    )
    verify_public(base, manifest, package, source)

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
