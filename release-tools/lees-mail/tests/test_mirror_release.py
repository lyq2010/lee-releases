import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mirror_release


class MirrorReleaseTests(unittest.TestCase):
    def setUp(self):
        self.assets = Path(__file__).resolve().parent / "fixtures"
        self.package = self.assets / "LeesMail_1.2.3_x64-setup.exe"
        self.msix = self.assets / "LeesMail_1.2.3_x64.msix"

    def manifest(self, **overrides):
        manifest = json.loads(
            (self.assets / mirror_release.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        manifest.update(overrides)
        return manifest

    def test_load_release_accepts_matching_assets(self):
        expected = self.manifest()

        manifest, manifest_path, package, msix = mirror_release.load_release(self.assets)

        self.assertEqual(expected, manifest)
        self.assertEqual(self.assets / mirror_release.MANIFEST_NAME, manifest_path)
        self.assertEqual(self.package, package)
        self.assertEqual(self.msix, msix)

    def test_load_release_rejects_hash_mismatch(self):
        invalid = self.manifest(sha256="0" * 64)

        with patch.object(Path, "read_text", return_value=json.dumps(invalid)):
            with self.assertRaisesRegex(SystemExit, "package hash or size mismatch"):
                mirror_release.load_release(self.assets)

    def test_load_release_rejects_unsafe_asset_name(self):
        invalid = self.manifest(package="../LeesMail.exe")

        with patch.object(Path, "read_text", return_value=json.dumps(invalid)):
            with self.assertRaisesRegex(SystemExit, "safe asset name"):
                mirror_release.load_release(self.assets)

    def test_write_mirror_manifest_updates_only_url(self):
        expected = self.manifest()
        manifest_path = Mock()

        mirror_release.write_mirror_manifest(
            expected, manifest_path, "https://mirror.example/releases", self.package
        )

        serialized = manifest_path.write_text.call_args.args[0]
        actual = json.loads(serialized)
        manifest_path.write_text.assert_called_once_with(serialized, encoding="utf-8")
        self.assertEqual(
            f"https://mirror.example/releases/{self.package.name}", actual["url"]
        )
        self.assertEqual("1.2.3", actual["version"])
        self.assertEqual(self.msix.name, actual["msixPackage"])

    def test_verify_public_sends_non_default_user_agent(self):
        expected = self.manifest()
        expected["url"] = "https://mirror.example/releases/LeesMail_1.2.3_x64-setup.exe"
        responses = [
            Mock(status=200, read=Mock(return_value=json.dumps(expected).encode("utf-8"))),
            Mock(status=200, read=Mock(return_value=b"")),
            Mock(status=200, read=Mock(return_value=b"")),
        ]
        contexts = []
        for response in responses:
            context = Mock()
            context.__enter__ = Mock(return_value=response)
            context.__exit__ = Mock(return_value=False)
            contexts.append(context)

        with patch.object(mirror_release.urllib.request, "urlopen", side_effect=contexts) as urlopen:
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "42"}, clear=False):
                mirror_release.verify_public(
                    "https://mirror.example/releases",
                    expected,
                    self.package,
                    self.msix,
                )

        self.assertEqual(3, urlopen.call_count)
        for call in urlopen.call_args_list:
            request = call.args[0]
            self.assertEqual(mirror_release.VERIFY_USER_AGENT, request.get_header("User-agent"))

    def test_verify_public_retries_transient_forbidden(self):
        expected = self.manifest()
        expected["url"] = "https://mirror.example/releases/LeesMail_1.2.3_x64-setup.exe"
        forbidden = urllib.error.HTTPError(
            "https://mirror.example/releases/latest-lees-mail.json",
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(),
        )
        success = Mock(status=200, read=Mock(return_value=json.dumps(expected).encode("utf-8")))
        head_ok = Mock(status=200, read=Mock(return_value=b""))
        success_ctx = Mock()
        success_ctx.__enter__ = Mock(return_value=success)
        success_ctx.__exit__ = Mock(return_value=False)
        head_ctx = Mock()
        head_ctx.__enter__ = Mock(return_value=head_ok)
        head_ctx.__exit__ = Mock(return_value=False)

        with patch.object(
            mirror_release.urllib.request,
            "urlopen",
            side_effect=[forbidden, success_ctx, head_ctx, head_ctx],
        ):
            with patch.object(mirror_release.time, "sleep") as sleep:
                with patch.dict(os.environ, {"GITHUB_RUN_ID": "42"}, clear=False):
                    mirror_release.verify_public(
                        "https://mirror.example/releases",
                        expected,
                        self.package,
                        self.msix,
                    )
                sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
