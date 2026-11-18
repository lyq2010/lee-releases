"""Recover only the pinned ONNX Runtime libraries and notices from the 1.0.0 packages."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

PACKAGES = {
    "windows-x86_64": (
        "lees-pdf-1.0.0-windows-x86_64-setup.exe",
        "da8187e094ce1bbf32801c62c2f12a8118b758cad9be70e79e69da678f6082ac",
        "onnxruntime-win-x64-1.30.0",
        ("onnxruntime.dll", "onnxruntime_providers_shared.dll"),
    ),
    "darwin-aarch64": (
        "lees-pdf-1.0.0-darwin-aarch64.app.tar.gz",
        "e17e07593122c7cfe1e5c7cbc65bb173dd833ff2a970b38ab3fcb53a6daca049",
        "onnxruntime-osx-arm64-1.30.0",
        ("libonnxruntime.1.30.0.dylib",),
    ),
}
NOTICES = {
    "ONNX-Runtime-MIT.txt": "LICENSE",
    "ONNX-Runtime-ThirdPartyNotices.txt": "ThirdPartyNotices.txt",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract_mac(archive, destination, members):
    found = set()
    with tarfile.open(archive, "r|gz") as package:
        for member in package:
            name = PurePosixPath(member.name)
            tail = "/".join(name.parts[1:])
            if tail not in members:
                continue
            if not member.isfile() or tail in found:
                raise ValueError("Unexpected ONNX input archive member")
            found.add(tail)
            with package.extractfile(member) as source:
                (destination / members[tail]).write_bytes(source.read())
    if found != set(members):
        raise ValueError("Verified macOS package is missing ONNX input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--target", choices=PACKAGES, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--seven-zip", type=Path)
    args = parser.parse_args()
    name, expected, directory, libraries = PACKAGES[args.target]
    args.scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "release", "download", "lees-pdf-v1.0.0", "--repo",
         "lyq2010/lee-releases", "--pattern", name, "--dir", str(args.scratch)],
        check=True,
    )
    archive = args.scratch / name
    if digest(archive) != expected:
        raise ValueError("Published package identity mismatch")
    pinned = {
        asset: (int(size.replace("_", "")), sha)
        for asset, size, sha in re.findall(
            r'file:\s*"([^"]+)",\s*bytes:\s*([\d_]+),\s*sha256:\s*"([0-9a-f]{64})"',
            (args.source / "crates/ocr-contract/src/assets.rs").read_text(encoding="utf-8"),
        )
    }
    with tempfile.TemporaryDirectory(dir=args.scratch) as folder:
        extracted = Path(folder)
        if args.target == "windows-x86_64":
            if args.seven_zip is None or not args.seven_zip.is_file():
                raise ValueError("7-Zip is required to extract the published NSIS installer")
            subprocess.run(
                [str(args.seven_zip), "e", "-y", "-r", f"-o{folder}",
                 str(archive), *libraries, *NOTICES],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        else:
            resources = "Contents/Resources/"
            members = {resources + "resources/ocr/scan-runtime/" + item: item for item in libraries}
            members.update({resources + "licenses/ocr-scan/" + item: item for item in NOTICES})
            extract_mac(archive, extracted, members)
        for item in libraries:
            path = extracted / item
            if (path.stat().st_size, digest(path)) != pinned[item]:
                raise ValueError("Recovered ONNX library differs from the fixed quality baseline")
        output = args.tools / "ocr-sdk" / "onnxruntime" / directory
        (output / "lib").mkdir(parents=True)
        for item in libraries:
            shutil.copyfile(extracted / item, output / "lib" / item)
        for item, target in NOTICES.items():
            shutil.copyfile(extracted / item, output / target)
    print("Pinned ONNX Runtime libraries and notices restored from the verified published package")


if __name__ == "__main__":
    main()
