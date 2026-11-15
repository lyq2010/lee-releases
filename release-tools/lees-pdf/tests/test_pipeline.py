"""Native candidate boundaries; failures occur before credentials or builds."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "release-tools/lees-pdf/build.ps1"
WORKFLOW = (ROOT / ".github/workflows/lees-pdf-release.yml").read_text("utf-8")


class PipelineTests(unittest.TestCase):
    def reject(self, target, tag, version, message):
        env = os.environ | {"RELEASE_TARGET": target, "SOURCE_TAG": tag, "RELEASE_VERSION": version}
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(BUILD), "-SourceRoot", str(ROOT),
             "-OutputRoot", str(ROOT / "never-created-output")],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse((ROOT / "never-created-output").exists())

    def test_rejects_macos_before_building_or_reading_credentials(self):
        self.reject("aarch64-apple-darwin", "v0.1.7", "0.1.7", "禁止回落到旧应用构建")

    def test_rejects_untrusted_tag_and_mismatched_version(self):
        for tag, version in (("main", "0.1.7"), ("v0.1.7", "0.1.8"), ("v01.1.7", "01.1.7")):
            with self.subTest(tag=tag, version=version):
                self.reject("windows-x86_64", tag, version, "源码Tag或版本无效")

    def test_manual_candidate_cannot_publish_or_mix_platforms(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("runs-on: windows-2025", WORKFLOW)
        self.assertIn("contents: read", WORKFLOW)
        self.assertNotIn("contents: write", WORKFLOW)
        for forbidden in ("tauri build", "gh release", "mirror.py", "prepare-jdk", "promote:"):
            self.assertNotIn(forbidden, WORKFLOW)
        self.assertIn("public-output/*", WORKFLOW)
        self.assertNotIn("path: I:/DevCache\n", WORKFLOW)

    def test_only_public_registry_archives_are_cached(self):
        self.assertEqual(WORKFLOW.count("uses: actions/cache@"), 1)
        self.assertIn("path: I:/DevCache/cargo/registry/cache/index.crates.io-*/*.crate", WORKFLOW)
        build = BUILD.read_text("utf-8")
        self.assertIn("build-native-candidate.ps1", build)
        self.assertIn("$row.sourceDirty", build)
        self.assertIn("$row.sourceRevision -ne $revision", build)
        self.assertIn("candidate-files.json", build)
        self.assertIn("windowsCertificateSha256", build)
        self.assertIn("--ignore-scripts", build)
        self.assertNotIn("tauri build", build)


if __name__ == "__main__":
    unittest.main()
