"""Keep only the latest Lee's Emby assets in a shared mirror bucket."""

from __future__ import annotations

import re
import urllib.parse
from typing import Callable, Iterable


ASSET_PATTERN = re.compile(
    r"(?:LeesEmby_(\d+\.\d+\.\d+)_x64-setup\.exe(?:\.minisig)?|"
    r"lees-emby_(\d+\.\d+\.\d+)_source\.zip)"
)


def version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise SystemExit(f"Invalid release version: {value}")
    return tuple(map(int, value.split(".")))


def old_assets(keys: Iterable[str], version: str, prefix: str = "") -> list[str]:
    current = version_tuple(version)
    root = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
    old = []
    for key in keys:
        if not key.startswith(root):
            continue
        match = ASSET_PATTERN.fullmatch(key[len(root):])
        if not match:
            continue
        asset_version = version_tuple(match.group(1) or match.group(2))
        if asset_version > current:
            raise SystemExit(f"Refusing to prune a mirror containing a newer release: {key}")
        if asset_version < current:
            old.append(key)
    return sorted(set(old))


def prune_old_assets(list_keys: Callable[[], list[str]], delete_key: Callable[[str], None],
                     version: str, prefix: str = "") -> None:
    old = old_assets(list_keys(), version, prefix)
    for key in old:
        print(f"Deleting old Lee's Emby asset: {key}", flush=True)
        delete_key(key)
    remaining = old_assets(list_keys(), version, prefix)
    if remaining:
        raise SystemExit(f"Old Lee's Emby assets remain after cleanup: {remaining}")
    print(f"Latest-only retention verified: {version}; deleted {len(old)} object(s)", flush=True)


def cos_keys(client, bucket: str, prefix: str) -> list[str]:
    keys = []
    marker = ""
    root = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
    while True:
        page = client.list_objects(Bucket=bucket, Prefix=root, Marker=marker, MaxKeys=1000)
        keys.extend(item["Key"] for item in page.get("Contents", []))
        if str(page.get("IsTruncated", "false")).lower() != "true":
            return keys
        next_marker = page.get("NextMarker")
        if not next_marker or next_marker == marker:
            raise SystemExit("COS returned an invalid pagination marker")
        marker = next_marker


def r2_objects_path(account_id: str, bucket: str) -> str:
    return f"/accounts/{urllib.parse.quote(account_id, safe='')}/r2/buckets/{urllib.parse.quote(bucket, safe='')}/objects"


def r2_keys(request, token: str, account_id: str, bucket: str) -> list[str]:
    keys = []
    params = {"per_page": "1000"}
    while True:
        page = request(token, "GET", r2_objects_path(account_id, bucket), params)
        keys.extend(item["key"] for item in page.get("result", []))
        info = page.get("result_info") or {}
        if not info.get("is_truncated"):
            return keys
        cursor = info.get("cursor")
        if not cursor or cursor == params.get("cursor"):
            raise SystemExit("R2 returned an invalid pagination cursor")
        params = {"per_page": "1000", "cursor": cursor}
