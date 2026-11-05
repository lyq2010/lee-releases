import importlib.util
import json
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("mirror", Path(__file__).resolve().parents[1] / "mirror_release.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "LeesEmby_1.9.0_x64-setup.exe"
        self.package.write_bytes(b"signed setup fixture")
        self.manifest = dict(version="1.9.0", platform="windows-x86_64", package=self.package.name,
            url="https://example.com/" + self.package.name, sha256=mirror.sha256(self.package),
            size=self.package.stat().st_size,
            certificateThumbprint="FA30417D52044ABBCC4E97AE9A306057A0DE0F1A", signature="signed fixture")
        self.write_manifest()

    def write_manifest(self):
        (self.root / mirror.MANIFEST_NAME).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_load_complete_release(self):
        self.assertEqual(mirror.load_release(self.root)[2], self.package)

    def test_drop_source_fields_without_requiring_archive(self):
        self.manifest["sourceArchive"] = "lees-emby_1.9.0_source.zip"
        self.manifest["sourceSha256"] = "A" * 64
        self.manifest["sourceSize"] = 1
        self.write_manifest()
        loaded = mirror.load_release(self.root)[0]
        self.assertNotIn("sourceArchive", loaded)
        self.assertNotIn("sourceSha256", loaded)
        self.assertNotIn("sourceSize", loaded)

    def test_reject_modified_installer(self):
        self.package.write_bytes(b"wrong")
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_reject_path_escape(self):
        self.manifest["package"] = "../other.exe"
        self.write_manifest()
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_reject_manifest_version_asset_disagreement(self):
        self.manifest["version"] = "1.9.1"
        self.write_manifest()
        with self.assertRaises(SystemExit):
            mirror.load_release(self.root)

    def test_cos_verifies_before_pruning_and_after_pruning(self):
        calls = []
        client = Mock()
        client.upload_file.side_effect = lambda **kwargs: calls.append(kwargs["Key"])
        client.put_object.side_effect = lambda **kwargs: calls.append(kwargs["Key"])
        sdk = types.SimpleNamespace(CosConfig=Mock(), CosS3Client=Mock(return_value=client))
        env = {"COS_PUBLIC_BASE_URL": "https://cos.example/releases", "TENCENT_COS_BUCKET": "fixture",
               "TENCENT_COS_REGION": "fixture", "TENCENT_COS_SECRET_ID": "fixture", "TENCENT_COS_SECRET_KEY": "fixture"}
        with patch.dict(mirror.os.environ, env), patch.dict(sys.modules, {"qcloud_cos": sdk}), \
             patch.object(mirror, "reject_downgrade"), \
             patch.object(mirror, "verify_public", side_effect=lambda *args: calls.append("verify")), \
             patch.object(mirror, "prune_old_assets", side_effect=lambda *args: calls.append("prune")):
            mirror.mirror_cos(self.root)
        self.assertEqual(calls, ["releases/" + self.package.name,
                                "releases/" + mirror.MANIFEST_NAME, "verify", "prune", "verify"])

    def test_publish_and_verify_before_pruning_then_verify_again(self):
        calls = []
        env = {"R2_PUBLIC_BASE_URL": "https://backup.example", "R2_BUCKET": "test",
               "CLOUDFLARE_API_TOKEN": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture"}
        with patch.dict(mirror.os.environ, env), patch.object(mirror, "wrangler_put", side_effect=lambda *args: calls.append(args[1])), \
             patch.object(mirror, "reject_downgrade"), \
             patch.object(mirror, "verify_public", side_effect=lambda *args: calls.append("verify")), \
             patch.object(mirror, "prune_old_assets", side_effect=lambda *args: calls.append("prune")):
            mirror.mirror_r2(self.root)
        self.assertEqual(calls, [self.package.name, mirror.MANIFEST_NAME, "verify", "prune", "verify"])

    def test_failed_verification_does_not_delete_old_versions(self):
        env = {"R2_PUBLIC_BASE_URL": "https://backup.example", "R2_BUCKET": "test",
               "CLOUDFLARE_API_TOKEN": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture"}
        with patch.dict(mirror.os.environ, env), patch.object(mirror, "wrangler_put"), \
             patch.object(mirror, "reject_downgrade"), \
             patch.object(mirror, "verify_public", side_effect=SystemExit("verify failed")), \
             patch.object(mirror, "prune_old_assets") as prune:
            with self.assertRaises(SystemExit):
                mirror.mirror_r2(self.root)
        prune.assert_not_called()

    def test_refuses_downgrade_before_upload(self):
        env = {"R2_PUBLIC_BASE_URL": "https://backup.example", "R2_BUCKET": "test",
               "CLOUDFLARE_API_TOKEN": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture"}
        with patch.dict(mirror.os.environ, env), patch.object(mirror, "wrangler_put") as upload, \
             patch.object(mirror, "reject_downgrade", side_effect=SystemExit("newer version")):
            with self.assertRaises(SystemExit):
                mirror.mirror_r2(self.root)
        upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
