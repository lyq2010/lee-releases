import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("mirror", Path(__file__).resolve().parents[1] / "mirror_release.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "LeesEmby_1.9.0_x64-setup.exe"
        self.source = self.root / "lees-emby_1.9.0_source.zip"
        self.package.write_bytes(b"signed setup fixture")
        self.source.write_bytes(b"source fixture")
        self.manifest = dict(version="1.9.0", platform="windows-x86_64", package=self.package.name,
            url="https://example.com/" + self.package.name, sha256=mirror.sha256(self.package),
            size=self.package.stat().st_size, sourceArchive=self.source.name,
            sourceSha256=mirror.sha256(self.source), sourceSize=self.source.stat().st_size,
            certificateThumbprint="FA30417D52044ABBCC4E97AE9A306057A0DE0F1A", signature="signed fixture")
        self.write_manifest()

    def write_manifest(self):
        (self.root / mirror.MANIFEST_NAME).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_load_complete_release(self):
        self.assertEqual(mirror.load_release(self.root)[2:], (self.package, self.source))

    def test_reject_missing_source(self):
        self.source.unlink()
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_reject_modified_source(self):
        self.source.write_bytes(b"wrong")
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_reject_modified_installer(self):
        self.package.write_bytes(b"wrong")
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_reject_path_escape(self):
        self.manifest["package"] = "../other.exe"
        self.write_manifest()
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_publish_manifest_last_without_deleting_old_versions(self):
        calls = []
        env = {"R2_PUBLIC_BASE_URL": "https://backup.example", "R2_BUCKET": "test",
               "CLOUDFLARE_API_TOKEN": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture"}
        with patch.dict(mirror.os.environ, env), patch.object(mirror, "wrangler_put", side_effect=lambda *args: calls.append(args[1])), \
             patch.object(mirror, "verify_public"), patch.object(mirror, "cloudflare_request") as api:
            mirror.mirror_r2(self.root)
        self.assertEqual(calls, [self.package.name, self.source.name, mirror.MANIFEST_NAME])
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
