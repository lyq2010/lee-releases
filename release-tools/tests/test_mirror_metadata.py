import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mirror_metadata import r2_objects, r2_path, verify_cos, verify_r2


class MetadataTests(unittest.TestCase):
    def test_cos_only_heads_and_requires_exact_sizes(self):
        client = Mock(spec=["head_object"])
        client.head_object.return_value = {"Content-Length": "12"}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            verify_cos(client, "fixture", {"prefix/feed.json": 12})
        client.head_object.assert_called_once_with(Bucket="fixture", Key="prefix/feed.json")
        self.assertIn("未验证", output.getvalue())
        with self.assertRaisesRegex(SystemExit, "size mismatch"):
            verify_cos(client, "fixture", {"prefix/feed.json": 13})

    def test_r2_listing_pagination_is_metadata_only(self):
        request = Mock(side_effect=[
            {"result": [{"key": "asset", "size": 11}], "result_info": {"is_truncated": True, "cursor": "next"}},
            {"result": [{"key": "asset-extra", "size": 12}]},
        ])
        verify_r2(request, "/objects", {"asset": 11})
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertEqual(call.args[:2], ("GET", "/objects"))
            self.assertEqual(call.args[2]["prefix"], "asset")
        self.assertEqual(request.call_args.args[2]["cursor"], "next")

    def test_missing_similarly_named_object_is_not_accepted(self):
        request = Mock(return_value={"result": [{"key": "feed.json.backup", "size": 12}]})
        with self.assertRaisesRegex(SystemExit, "missing"):
            verify_r2(request, "/objects", {"feed.json": 12})

    def test_bad_size_is_rejected(self):
        request = Mock(return_value={"result": [{"key": "asset", "size": 13}]})
        with self.assertRaisesRegex(SystemExit, "size mismatch"):
            verify_r2(request, "/objects", {"asset": 12})

    def test_truncated_listing_without_cursor_fails(self):
        request = Mock(return_value={"result": [], "result_info": {"is_truncated": True}})
        with self.assertRaisesRegex(SystemExit, "cursor"):
            r2_objects(request, "/objects", "asset")

    def test_repeated_cursor_fails(self):
        request = Mock(return_value={"result": [], "result_info": {"cursor": "same"}})
        with self.assertRaisesRegex(SystemExit, "cursor"):
            r2_objects(request, "/objects", "asset")

    def test_r2_account_and_bucket_are_escaped(self):
        self.assertEqual(r2_path("a/b", "b/c"), "/accounts/a%2Fb/r2/buckets/b%2Fc/objects")


if __name__ == "__main__":
    unittest.main()
