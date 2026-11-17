"""Native dual-platform release boundaries; failures occur before credentials or builds."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "release-tools/lees-pdf/build.ps1"
WORKFLOW = (ROOT / ".github/workflows/lees-pdf-release.yml").read_text("utf-8")
PWSH = shutil.which("pwsh")


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PWSH:
            raise unittest.SkipTest("pwsh is required for build.ps1 boundary checks")

    def local_target(self):
        if sys.platform == "darwin":
            return "darwin-aarch64"
        if sys.platform.startswith("win"):
            return "windows-x86_64"
        self.fail("pipeline boundary checks require Windows or macOS")

    def foreign_target(self):
        return "windows-x86_64" if self.local_target() == "darwin-aarch64" else "darwin-aarch64"

    def reject(self, target, tag, version, message):
        env = os.environ | {
            "RELEASE_TARGET": target,
            "SOURCE_TAG": tag,
            "RELEASE_VERSION": version,
            "LEESPDF_COS_BASE_URL": "https://example.invalid/",
            "RUNNER_TEMP": str(ROOT / "never-created-runner-temp"),
        }
        result = subprocess.run(
            [PWSH, "-NoProfile", "-File", str(BUILD), "-SourceRoot", str(ROOT),
             "-OutputRoot", str(ROOT / "never-created-output")],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr + result.stdout)
        self.assertFalse((ROOT / "never-created-output").exists())

    def test_rejects_untrusted_tag_and_mismatched_version(self):
        target = self.local_target()
        for tag, version in (("main", "0.1.7"), ("v0.1.7", "0.1.8"), ("v01.1.7", "01.1.7")):
            with self.subTest(tag=tag, version=version):
                self.reject(target, tag, version, "源码Tag或版本无效")

    def test_rejects_platform_mismatch_before_credentials(self):
        self.reject(self.foreign_target(), "v1.0.0", "1.0.0", "构建平台不匹配")

    def test_build_progress_and_archive_cache_survive_failures(self):
        build = BUILD.read_text("utf-8")
        self.assertIn("logged_build.py", build)
        self.assertNotIn("*>> $diagnostics", build)
        self.assertNotIn("*> $diagnostics", build)
        self.assertIn("actions/cache/restore@v5", WORKFLOW)
        self.assertIn("actions/cache/save@v5", WORKFLOW)
        self.assertIn("always() && steps.cargo-cache.outputs.cache-hit", WORKFLOW)
        self.assertIn("timeout-minutes: 210", WORKFLOW)
        self.assertIn("always() && inputs.promote", WORKFLOW)
        self.assertNotIn("正常构建会直接发布", WORKFLOW)
        self.assertIn("if(!$env:CARGO_HOME)", build)

    def test_full_release_workflow_restored(self):
        self.assertIn("name: Lee's PDF Release", WORKFLOW)
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("promote:", WORKFLOW)
        self.assertIn("platform:", WORKFLOW)
        self.assertIn("windows-2025", WORKFLOW)
        self.assertIn("macos-26", WORKFLOW)
        self.assertIn("darwin-aarch64", WORKFLOW)
        self.assertIn("mirror.py", WORKFLOW)
        self.assertIn("manifest.mjs", WORKFLOW)
        for required in ("prepare-draft:", "draft:", "mirror:", "promote:"):
            self.assertIn(required, WORKFLOW)
        self.assertNotIn("tauri build", WORKFLOW)
        self.assertNotIn("prepare-jdk", WORKFLOW)
        self.assertNotIn("TAURI_SIGNING", WORKFLOW)
        self.assertIn("LEES_UPDATER_PRIVATE_KEY: ${{ secrets.LEESPDF_UPDATER_PRIVATE_KEY }}", WORKFLOW)
        build = BUILD.read_text("utf-8")
        self.assertIn("build-native-macos-release.ps1", build)
        self.assertIn("build-native-candidate.ps1", build)
        self.assertIn("release-files.json", build)
        for forbidden in ("npm install --prefix $signer", "UpdaterSigner", "@tauri-apps/cli", "tauri build"):
            self.assertNotIn(forbidden, build)


class WorkflowStaticTests(unittest.TestCase):
    def test_workflow_name_and_matrix_without_pwsh(self):
        self.assertIn("name: Lee's PDF Release", WORKFLOW)
        self.assertIn("macos-26", WORKFLOW)
        self.assertIn("build-native-macos-release.ps1", BUILD.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
