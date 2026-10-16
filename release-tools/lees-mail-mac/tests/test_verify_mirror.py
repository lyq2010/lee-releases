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


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_mirror import load_release, verify_sizes

WORKFLOW = (ROOT / ".github/workflows/lees-mail-mac-release.yml").read_text()


def snippet(start):
    body = WORKFLOW.split(start + "\n", 1)[1].split("\n          PY", 1)[0]
    return textwrap.dedent(body)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        # Keep synthetic temporary files; do not delete files during verification.
        self.directory = Path(tempfile.mkdtemp(prefix="lees-mail-mac-mirror-"))
        self.assets = self.directory / "assets"
        self.assets.mkdir()
        self.version = "1.2.3"
        self.dmg = "LeesMail-1.2.3-arm64.dmg"
        self.manifest_name = "latest-lees-mail-electron.json"
        self.base = "https://mirror.example/releases"
        payload = b"synthetic dmg"
        (self.assets / self.dmg).write_bytes(payload)
        (self.assets / f"{self.dmg}.minisig").write_bytes(b"synthetic signature")
        self.manifest = {
            "version": self.version,
            "downloadURL": f"{self.base}/{self.dmg}",
            "minisignSignatureURL": f"{self.base}/{self.dmg}.minisig",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "downloadSize": len(payload),
        }
        self.write_manifest()
        self.env = {
            "VERSION": self.version, "MANIFEST_NAME": self.manifest_name,
            "COS_PUBLIC_BASE_URL": self.base, "R2_PUBLIC_BASE_URL": self.base,
            "GITHUB_WORKSPACE": str(self.directory), "R2_BUCKET": "fixture",
            "CLOUDFLARE_API_TOKEN": "synthetic-token",
            "TENCENT_COS_REGION": "fixture", "TENCENT_COS_BUCKET": "fixture",
            "TENCENT_COS_SECRET_ID": "fixture", "TENCENT_COS_SECRET_KEY": "fixture",
        }
        # Any accidental real network operation must fail immediately.
        network = patch("socket.create_connection", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def write_manifest(self):
        (self.assets / self.manifest_name).write_text(json.dumps(self.manifest))

    def load(self):
        return load_release(self.assets, self.version, self.base, self.manifest_name)

    def execute(self, source):
        previous = Path.cwd()
        try:
            os.chdir(self.directory)
            with patch.dict(os.environ, self.env), contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, "workflow-snippet", "exec"), {})
        finally:
            os.chdir(previous)

    def test_local_release_rejects_invalid_version_urls_size_and_hash(self):
        for field, value in (
            ("version", "9.9.9"), ("downloadURL", "https://wrong.example/a.dmg"),
            ("minisignSignatureURL", "https://wrong.example/a.minisig"),
            ("downloadSize", 1), ("sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                original = self.manifest[field]
                self.manifest[field] = value
                self.write_manifest()
                with self.assertRaises(SystemExit):
                    self.load()
                self.manifest[field] = original

    def test_empty_signature_rejected(self):
        (self.assets / f"{self.dmg}.minisig").write_bytes(b"")
        with self.assertRaisesRegex(SystemExit, "为空"):
            self.load()

    def test_metadata_missing_or_mismatch_rejected(self):
        expected = self.load()
        for name in expected:
            for replacement in (None, expected[name] + 1):
                with self.subTest(name=name, size=replacement):
                    actual = dict(expected)
                    if replacement is None:
                        actual.pop(name)
                    else:
                        actual[name] = replacement
                    with self.assertRaisesRegex(SystemExit, "缺失或大小不符"):
                        verify_sizes(expected, actual)

    def cos_client(self):
        sizes = self.load()
        client = Mock(spec=["upload_file", "put_object", "head_object", "list_objects", "delete_object"])
        client.head_object.side_effect = lambda **kw: {
            "Content-Length": str(sizes[kw["Key"].removeprefix("releases/")])}
        client.list_objects.return_value = {"Contents": [], "IsTruncated": False}
        return client

    def execute_cos(self, client):
        sdk = types.SimpleNamespace(CosConfig=Mock(), CosS3Client=Mock(return_value=client))
        with patch.dict(sys.modules, {"qcloud_cos": sdk}):
            self.execute(snippet('          cat > "$RUNNER_TEMP/cos_step.py" << \'PY\''))

    def test_cos_uploads_then_heads_all_three_objects_without_get(self):
        client = self.cos_client()
        self.execute_cos(client)
        self.assertEqual(client.upload_file.call_count, 2)
        client.put_object.assert_called_once()
        self.assertEqual({c.kwargs["Key"] for c in client.head_object.call_args_list},
                         {f"releases/{name}" for name in self.load()})
        calls = [call[0] for call in client.mock_calls]
        self.assertLess(calls.index("put_object"), calls.index("head_object"))

    def test_cos_local_mismatch_stops_before_upload(self):
        client = self.cos_client()
        self.manifest["version"] = "9.9.9"
        self.write_manifest()
        with self.assertRaises(SystemExit):
            self.execute_cos(client)
        client.upload_file.assert_not_called()
        client.put_object.assert_not_called()

    def execute_r2(self, sizes):
        requests = []

        def urlopen(request, timeout):
            parsed = urllib.parse.urlsplit(request.full_url)
            self.assertEqual(parsed.netloc, "api.cloudflare.com")
            self.assertEqual(parsed.path, "/client/v4/accounts/account/r2/buckets/fixture/objects")
            self.assertEqual(request.get_method(), "GET")
            params = urllib.parse.parse_qs(parsed.query)
            requests.append(params)
            names = [name for name in sizes if name.startswith(params["prefix"][0])]
            # Force a second page to exercise release object pagination.
            cursor = ""
            if len(names) > 1:
                if "cursor" in params:
                    names = names[1:]
                else:
                    names, cursor = names[:1], "page-2"
            data = {"success": True, "result": [{"key": n, "size": sizes[n]} for n in names],
                    "result_info": {"cursor": cursor}}
            return io.BytesIO(json.dumps(data).encode())

        with patch("urllib.request.urlopen", side_effect=urlopen), patch.object(sys, "argv", ["verify", "account"]):
            self.execute(snippet('          python3 - "$account_id" <<\'PY\''))
        return requests

    def test_r2_only_reads_management_list_metadata_with_pagination(self):
        requests = self.execute_r2(self.load())
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[-1]["prefix"], [self.manifest_name])

    def test_r2_missing_or_wrong_size_fails(self):
        for name in self.load():
            with self.subTest(name=name):
                sizes = self.load()
                sizes[name] += 1
                with self.assertRaisesRegex(SystemExit, "大小不符"):
                    self.execute_r2(sizes)
        with self.assertRaisesRegex(SystemExit, "缺失"):
            self.execute_r2({})

    def test_r2_rewrites_and_validates_local_manifest_before_upload(self):
        self.env["R2_PUBLIC_BASE_URL"] = "https://backup.example"
        source = WORKFLOW.split("# sha256 与 downloadSize 描述的是同一个文件，保持不变。", 1)[1]
        source = textwrap.dedent(source.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        self.execute(source)
        manifest = json.loads((self.assets / self.manifest_name).read_text())
        self.assertEqual(manifest["downloadURL"], f"https://backup.example/{self.dmg}")
        self.assertEqual(manifest["sha256"], self.manifest["sha256"])
        self.manifest["sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(SystemExit, "SHA-256"):
            self.execute(source)

    def test_workflow_has_no_public_object_downloads_or_automatic_release_trigger(self):
        self.assertNotRegex(WORKFLOW, r"(?m)^  (push|release|workflow_run):")
        mirrors = WORKFLOW.split("  cos-lees-mail-mac-mirror:", 1)[1]
        self.assertNotIn("?verify=", mirrors)
        self.assertNotIn("r2 object get", mirrors)
        self.assertEqual(mirrors.count("curl -fsS"), 1)  # Cloudflare account lookup only.
        for job in re.split(r"(?m)^  (?:cos|r2)-lees-mail-mac-mirror:", WORKFLOW)[1:]:
            self.assertIn("path: release-repo", job)


if __name__ == "__main__":
    unittest.main()
