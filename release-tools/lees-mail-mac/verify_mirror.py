"""Validate local Mac release assets and remote sizes without reading remote bodies."""
import hashlib
import json
from pathlib import Path


def load_release(assets, version, base, manifest_name):
    assets = Path(assets)
    dmg = f"LeesMail-{version}-arm64.dmg"
    manifest = json.loads((assets / manifest_name).read_text(encoding="utf-8"))
    if manifest["version"] != version:
        raise SystemExit("本地清单版本不符")
    for field, name in (("downloadURL", dmg), ("minisignSignatureURL", f"{dmg}.minisig")):
        if manifest[field] != f"{base}/{name}":
            raise SystemExit(f"本地清单 {field} 与目标通道不符")
    sizes = {name: (assets / name).stat().st_size
             for name in (dmg, f"{dmg}.minisig", manifest_name)}
    if any(size <= 0 for size in sizes.values()):
        raise SystemExit("本地发行物为空")
    with (assets / dmg).open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if manifest["downloadSize"] != sizes[dmg] or manifest["sha256"] != digest:
        raise SystemExit("本地 DMG 大小或 SHA-256 与清单不符")
    return sizes


def verify_sizes(expected, actual):
    for name, size in expected.items():
        if name not in actual or int(actual[name]) != size:
            raise SystemExit(f"远端对象缺失或大小不符: {name}")
    print("远端对象存在且大小匹配；远端正文、版本及哈希未验证（禁止下载补验）。")
