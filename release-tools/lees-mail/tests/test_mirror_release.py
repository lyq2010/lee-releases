import json
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
