"""Execute the actual toolbox mirror snippets with synthetic files and metadata APIs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import textwrap
import types
import unittest
import urllib.parse
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release-tools"))


class WorkflowMirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="toolbox-mirror-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.env = dict(VERSION="1.2.3", COS_PUBLIC_BASE_URL="https://cos.example/prefix",
                        R2_PUBLIC_BASE_URL="https://backup.example", GITHUB_WORKSPACE=str(self.root),
                        TENCENT_COS_BUCKET="fixture", TENCENT_COS_REGION="fixture",
                        TENCENT_COS_SECRET_ID="fixture", TENCENT_COS_SECRET_KEY="fixture",
                        R2_BUCKET="fixture", CLOUDFLARE_API_TOKEN="fixture")
        network = patch("socket.create_connection", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def fixture(self, product):
        native = product == "native"
        filename = "native-release.yml" if native else "lees-system-toolbox-release.yml"
        self.workflow = (ROOT / ".github/workflows" / filename).read_text()
        self.asset = "Lee.s.Toolbox.Mac_1.2.3_macOS_arm64.dmg" if native else "lees-system-toolbox_1.2.3_x64-setup.exe"
        self.feed = "latest-native.json" if native else "latest-lees-system-toolbox.json"
        payload = b"synthetic release artifact"
        (self.root / "assets" / self.asset).write_bytes(payload)
        if native:
            self.manifest = {"version": "1.2.3", "platforms": {"darwin-aarch64-native": {
                "url": f"https://github.example/{self.asset}", "signature": "synthetic signature"}}}
        else:
            self.manifest = {"version": "1.2.3", "platform": "windows-x86_64", "certificateThumbprint": "fixture",
                             "url": f"https://github.example/{self.asset}", "size": len(payload),
                             "sha256": hashlib.sha256(payload).hexdigest()}
        self.write_manifest()

    def write_manifest(self):
        (self.root / "assets" / self.feed).write_text(json.dumps(self.manifest))

    def execute(self, source):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env), contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, "workflow-snippet", "exec"), {})
        finally:
            os.chdir(previous)

    def cos(self, bad_size=False):
        source = self.workflow.split('cat > "$RUNNER_TEMP/cos_step.py" << \'PY\'\n', 1)[1]
        source = textwrap.dedent(source.split("\n          PY", 1)[0])
        objects = {}
        client = Mock(spec=["upload_file", "put_object", "head_object", "list_objects", "delete_object"])
        client.upload_file.side_effect = lambda **kw: objects.update({kw["Key"]: Path(kw["LocalFilePath"]).stat().st_size})
        client.put_object.side_effect = lambda **kw: objects.update({kw["Key"]: len(kw["Body"])})
        client.head_object.side_effect = lambda **kw: {"Content-Length": objects[kw["Key"]] + int(bad_size)}
        client.list_objects.return_value = {"Contents": []}
        sdk = types.SimpleNamespace(CosConfig=Mock(), CosS3Client=Mock(return_value=client))
        with patch.dict(sys.modules, {"qcloud_cos": sdk}):
            try:
                self.execute(source)
            finally:
                self.client = client
        self.assertEqual(client.head_object.call_count, 2)
        self.assertEqual(set(objects), {f"prefix/{self.asset}", f"prefix/{self.feed}"})

    def r2(self, bad_size=False):
        source = self.workflow.split("  r2-", 1)[1]
        scripts = [textwrap.dedent(s) for s in re.findall(r"<<'PY'\n(.*?)\n          PY", source, re.S)]
        self.execute(scripts[0])
        methods = []

        def urlopen(req, timeout):
            parsed = urllib.parse.urlsplit(req.full_url)
            self.assertEqual(parsed.netloc, "api.cloudflare.com")
            self.assertEqual(parsed.path, "/client/v4/accounts/account/r2/buckets/fixture/objects")
            self.assertEqual(req.get_method(), "GET")
            methods.append(req.get_method())
            params = urllib.parse.parse_qs(parsed.query)
            items = [{"key": p.name, "size": p.stat().st_size + int(bad_size)}
                     for p in (self.root / "assets").iterdir() if p.name.startswith(params["prefix"][0])]
            return io.BytesIO(json.dumps({"success": True, "result": items}).encode())

        with patch("urllib.request.urlopen", side_effect=urlopen), patch.object(sys, "argv", ["verify", "account"]):
            self.execute(scripts[1])
        self.assertGreaterEqual(len(methods), 2)

    def test_cos_metadata_verification_for_both_toolboxes(self):
        for product in ("native", "system"):
            with self.subTest(product=product):
                self.fixture(product)
                self.cos()

    def test_r2_management_metadata_for_both_toolboxes(self):
        for product in ("native", "system"):
            with self.subTest(product=product):
                self.fixture(product)
                self.r2()

    def test_cos_mismatch_stops_before_cleanup(self):
        for product in ("native", "system"):
            with self.subTest(product=product):
                self.fixture(product)
                with self.assertRaisesRegex(SystemExit, "size mismatch"):
                    self.cos(bad_size=True)
                self.client.delete_object.assert_not_called()
                self.client.list_objects.assert_not_called()

    def test_r2_mismatch_stops_before_cleanup(self):
        for product in ("native", "system"):
            with self.subTest(product=product):
                self.fixture(product)
                with self.assertRaisesRegex(SystemExit, "size mismatch"):
                    self.r2(bad_size=True)

    def test_wrong_local_version_stops_before_upload(self):
        for product in ("native", "system"):
            with self.subTest(product=product):
                self.fixture(product)
                self.manifest["version"] = "9.9.9"
                self.write_manifest()
                with self.assertRaises(SystemExit):
                    self.cos()
                self.client.upload_file.assert_not_called()
                self.client.put_object.assert_not_called()
                with self.assertRaises(SystemExit):
                    self.r2()


if __name__ == "__main__":
    unittest.main()
