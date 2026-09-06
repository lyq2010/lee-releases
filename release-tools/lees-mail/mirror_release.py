#!/usr/bin/env python3
"""Publish a Lee's Mail release mirror and verify its public update feed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MANIFEST_NAME = "latest-lees-mail.json"
PUBLIC_FIELDS = (
    "version",
    "platform",
    "package",
    "url",
    "sha256",
    "size",
    "certificateThumbprint",
    "msixPackage",
    "msixSha256",
    "msixSize",
)


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
    msix_name = safe_asset_name(manifest.get("msixPackage"), "msixPackage")
    package_path = assets / package_name
    msix_path = assets / msix_name
    if not package_path.is_file() or not msix_path.is_file():
        raise SystemExit("Lee's Mail release assets are incomplete")

    source_url_name = Path(urllib.parse.urlparse(str(manifest.get("url", ""))).path).name
    if source_url_name != package_name:
        raise SystemExit("Manifest package and URL disagree")
    if sha256(package_path) != str(manifest.get("sha256", "")).upper() or package_path.stat().st_size != manifest.get("size"):
        raise SystemExit("Lee's Mail package hash or size mismatch")
    if sha256(msix_path) != str(manifest.get("msixSha256", "")).upper() or msix_path.stat().st_size != manifest.get("msixSize"):
        raise SystemExit("Lee's Mail MSIX hash or size mismatch")
    if manifest.get("platform") != "windows-x86_64" or not manifest.get("certificateThumbprint"):
        raise SystemExit("Lee's Mail manifest identity fields are invalid")
    return manifest, manifest_path, package_path, msix_path


def write_mirror_manifest(manifest: dict[str, Any], manifest_path: Path, base: str, package: Path) -> None:
    manifest["url"] = f"{base}/{package.name}"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_public(base: str, expected: dict[str, Any], package: Path, msix: Path) -> None:
    run_id = urllib.parse.quote(os.environ.get("GITHUB_RUN_ID", "manual"), safe="")
    with urllib.request.urlopen(f"{base}/{MANIFEST_NAME}?verify={run_id}", timeout=30) as response:
        published = json.loads(response.read().decode("utf-8"))
    mismatches = [field for field in PUBLIC_FIELDS if published.get(field) != expected.get(field)]
    if mismatches:
        raise SystemExit(f"Published Lee's Mail manifest mismatch: {', '.join(mismatches)}")

    for asset in (package, msix):
        request = urllib.request.Request(
            f"{base}/{asset.name}?verify={run_id}",
            method="HEAD",
            headers={"Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise SystemExit(f"Lee's Mail mirror asset is not publicly available: {asset.name}")


def mirror_cos(assets: Path) -> None:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as error:
        raise SystemExit("cos-python-sdk-v5 is required for the COS mirror") from error

    manifest, manifest_path, package, msix = load_release(assets)
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
        )
    )

    client.upload_file(Bucket=bucket, LocalFilePath=str(package), Key=object_key(package.name), EnableMD5=False)
    client.upload_file(Bucket=bucket, LocalFilePath=str(msix), Key=object_key(msix.name), EnableMD5=False)
    write_mirror_manifest(manifest, manifest_path, base, package)
    client.put_object(
        Bucket=bucket,
        Body=manifest_path.read_bytes(),
        Key=object_key(MANIFEST_NAME),
        ContentType="application/json; charset=utf-8",
    )
    verify_public(base, manifest, package, msix)

    current = {object_key(package.name), object_key(msix.name)}
    marker = ""
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": object_key("LeesMail_"), "MaxKeys": 1000}
        if marker:
            kwargs["Marker"] = marker
        listed = client.list_objects(**kwargs)
        for item in listed.get("Contents", []) or []:
            key = item.get("Key", "")
            if key not in current and (key.endswith("_x64-setup.exe") or key.endswith("_x64.msix")):
                client.delete_object(Bucket=bucket, Key=key)
                print(f"Deleted old Lee's Mail mirror: {key}")
        if listed.get("IsTruncated") not in ("true", True):
            break
        marker = listed.get("NextMarker") or ""
        if not marker:
            raise SystemExit("COS listing was truncated without a marker")
    print("COS Lee's Mail mirror complete")


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
    manifest, manifest_path, package, msix = load_release(assets)
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
    wrangler_put(bucket, package.name, package, None, command_env)
    wrangler_put(bucket, msix.name, msix, None, command_env)
    write_mirror_manifest(manifest, manifest_path, base, package)
    wrangler_put(bucket, MANIFEST_NAME, manifest_path, "application/json; charset=utf-8", command_env)
    verify_public(base, manifest, package, msix)

    bucket_path = (
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/r2/buckets/"
        f"{urllib.parse.quote(bucket, safe='')}/objects"
    )
    cursor = ""
    stale: list[str] = []
    while True:
        params = {"prefix": "LeesMail_", "per_page": "1000"}
        if cursor:
            params["cursor"] = cursor
        data = cloudflare_request(token, "GET", bucket_path, params)
        for item in data.get("result") or []:
            key = item.get("key", "")
            if key not in (package.name, msix.name) and (key.endswith("_x64-setup.exe") or key.endswith("_x64.msix")):
                stale.append(key)
        info = data.get("result_info") or {}
        if not info.get("is_truncated"):
            break
        cursor = info.get("cursor") or ""
        if not cursor:
            raise SystemExit("R2 listing was truncated without a cursor")
    for key in stale:
        cloudflare_request(token, "DELETE", f"{bucket_path}/{urllib.parse.quote(key, safe='/')}")
        print(f"Deleted old Lee's Mail mirror: {key}")
    print("R2 Lee's Mail mirror complete")


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
