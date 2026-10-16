import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

prune = types.SimpleNamespace(cloudflare_request=Mock(), prune_cos=Mock(), prune_r2=Mock())
spec = importlib.util.spec_from_file_location("music_mirror", Path(__file__).resolve().parents[1] / "mirror.py")
mirror = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"prune": prune}):
    spec.loader.exec_module(mirror)


class MusicMirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lees-music-mirror-test-")
        self.addCleanup(self.temp.cleanup)
        self.assets = Path(self.temp.name) / "assets"
        self.assets.mkdir()
        self.version = "1.0.5"
        self.apk = self.assets / "lees-music-1.0.5.apk"
        self.apk.write_bytes(b"synthetic apk")
        self.checksum = self.assets / "lees-music-1.0.5-SHA256SUMS.txt"
        self.checksum.write_text(f"{mirror.digest(self.apk)}  {self.apk.name}\n")
        self.manifest = {"version": self.version, "versionCode": 105, "apk": self.apk.name,
                         "sha256": mirror.digest(self.apk), "size": self.apk.stat().st_size}
        (self.assets / mirror.MANIFEST).write_text(json.dumps(self.manifest))
        guard = patch("socket.create_connection", side_effect=AssertionError("network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_local_apk_and_checksum_validation(self):
        manifest, files, paths = mirror.load_release(self.assets)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(files, [self.apk, self.checksum])
        self.assertEqual(set(paths), {self.apk.name, self.checksum.name, mirror.MANIFEST})
        self.checksum.write_text("0" * 64 + f"  {self.apk.name}\n")
        with self.assertRaisesRegex(SystemExit, "checksum"):
            mirror.load_release(self.assets)

    def test_modified_apk_is_rejected(self):
        self.apk.write_bytes(b"wrong")
        with self.assertRaisesRegex(SystemExit, "integrity"):
            mirror.load_release(self.assets)

    def test_newer_asset_prevents_downgrade_without_body_read(self):
        with self.assertRaisesRegex(SystemExit, "newer"):
            mirror.reject_replacement({"lees-music-1.0.6.apk": {}}, self.version, {})

    def test_same_version_uses_md5_etags_or_stops(self):
        _, _, paths = mirror.load_release(self.assets)
        objects = {name: {"etag": f'"{mirror.digest(path, "md5")}"'} for name, path in paths.items()}
        mirror.reject_replacement(objects, self.version, paths)
        for etag in ("0" * 32, "multipart-2", ""):
            with self.subTest(etag=etag):
                objects[self.apk.name]["etag"] = etag
                with self.assertRaisesRegex(SystemExit, "unverified"):
                    mirror.reject_replacement(objects, self.version, paths)

    def run_r2(self, verify):
        loaded = mirror.load_release(self.assets)
        env = {"CLOUDFLARE_API_TOKEN": "fixture", "CLOUDFLARE_ACCOUNT_ID": "fixture"}
        with patch.dict(os.environ, env), patch.object(mirror, "load_release", return_value=loaded), \
             patch.object(mirror, "r2_objects", return_value={}), \
             patch.object(mirror, "verify_r2", side_effect=verify), \
             patch.object(mirror.subprocess, "run") as upload, patch.object(mirror, "prune_r2") as cleanup:
            try:
                mirror.main("r2")
            finally:
                self.upload_calls = upload.call_args_list
                self.pruned = cleanup.called

    def test_r2_verifies_assets_before_feed_and_cleanup(self):
        events = []
        self.run_r2(lambda *args: events.append(set(args[2])))
        self.assertEqual(len(self.upload_calls), 3)
        self.assertEqual(events[0], {self.apk.name, self.checksum.name})
        self.assertIn(mirror.MANIFEST, events[1])
        self.assertTrue(self.pruned)
        for call in self.upload_calls:
            self.assertEqual(call.args[0][3:6], ["r2", "object", "put"])

    def test_failed_asset_metadata_prevents_feed_and_cleanup(self):
        with self.assertRaisesRegex(SystemExit, "size mismatch"):
            self.run_r2(SystemExit("size mismatch"))
        self.assertEqual(len(self.upload_calls), 2)
        self.assertFalse(self.pruned)

    def run_cos(self, verify):
        class Missing(Exception):
            def get_status_code(self):
                return 404
        client = Mock(spec=["head_object", "put_object"])
        client.head_object.side_effect = Missing()
        sdk = types.SimpleNamespace(CosConfig=Mock(), CosS3Client=Mock(return_value=client))
        loaded = mirror.load_release(self.assets)
        env = {"TENCENT_COS_REGION": "fixture", "TENCENT_COS_BUCKET": "fixture",
               "TENCENT_COS_SECRET_ID": "fixture", "TENCENT_COS_SECRET_KEY": "fixture"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {
            "qcloud_cos": sdk, "qcloud_cos.cos_exception": types.SimpleNamespace(CosServiceError=Missing)
        }), patch.object(mirror, "load_release", return_value=loaded), \
             patch.object(mirror, "cos_objects", return_value={}), \
             patch.object(mirror, "verify_cos", side_effect=verify), patch.object(mirror, "prune_cos") as cleanup:
            try:
                mirror.main("cos")
            finally:
                self.cos_uploads = client.put_object.call_args_list
                self.pruned = cleanup.called

    def test_cos_missing_feed_can_publish_after_metadata_verification(self):
        events = []
        self.run_cos(lambda *args: events.append(set(args[2])))
        self.assertEqual([c.kwargs["Key"] for c in self.cos_uploads],
                         [self.apk.name, self.checksum.name, mirror.MANIFEST])
        self.assertNotIn(mirror.MANIFEST, events[0])
        self.assertIn(mirror.MANIFEST, events[1])
        self.assertTrue(self.pruned)

    def test_cos_metadata_failure_prevents_feed_and_cleanup(self):
        with self.assertRaisesRegex(SystemExit, "size mismatch"):
            self.run_cos(SystemExit("size mismatch"))
        self.assertEqual(len(self.cos_uploads), 2)
        self.assertFalse(self.pruned)

    def test_cos_list_only_preserves_pagination_and_etags(self):
        client = Mock(spec=["list_objects"])
        client.list_objects.side_effect = [
            {"Contents": [{"Key": self.apk.name, "ETag": "abc"}], "IsTruncated": True, "NextMarker": "next"},
            {"Contents": []},
        ]
        self.assertEqual(mirror.cos_objects(client, "fixture"), {self.apk.name: {"etag": "abc"}})
        self.assertEqual(client.list_objects.call_args.kwargs["Marker"], "next")


if __name__ == "__main__":
    unittest.main()
