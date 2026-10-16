"""Mirror verification must never fetch object bodies, including in-memory streams."""
import importlib.util
from pathlib import Path
import sys
import urllib.error
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('metadata_mirror', SCRIPTS / 'mirror.py')
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class MetadataPolicyTests(unittest.TestCase):
    def test_public_verification_uses_head_and_never_reads_body(self):
        response = MagicMock()
        response.headers = {'ETag': '\"' + 'a' * 32 + '\"', 'Content-Length': '123'}
        response.__enter__.return_value = response
        response.read.side_effect = AssertionError('Object body downloads are forbidden')
        with patch.object(mirror.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            actual = mirror.public_identity('https://cos.example/asset')
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'HEAD')
            self.assertFalse(request.has_header('Range'))
            response.read.assert_not_called()
            self.assertEqual(actual, ('a' * 32, 123))


    def test_missing_or_unsupported_metadata_never_falls_back_to_get(self):
        for headers in ({}, {'ETag': 'W/"' + 'a' * 32 + '"', 'Content-Length': '10'},
                        {'ETag': '"' + 'a' * 32 + '-2"', 'Content-Length': '10'},
                        {'ETag': '"' + 'a' * 32 + '"', 'Content-Length': '-1'}):
            with self.subTest(headers=headers), patch.object(mirror.urllib.request, 'build_opener') as opener:
                response = MagicMock()
                response.headers = headers
                response.__enter__.return_value = response
                opener.return_value.open.return_value = response
                with self.assertRaisesRegex(RuntimeError, 'insufficient'):
                    mirror.public_identity('https://r2.example/asset')
                self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertEqual(opener.return_value.open.call_args.args[0].get_method(), 'HEAD')
                response.read.assert_not_called()

    def test_http_errors_never_fall_back_to_get(self):
        for status in (404, 403, 500):
            with self.subTest(status=status), patch.object(mirror.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = urllib.error.HTTPError('https://cos.example/asset', status, '', {}, None)
                if status == 404:
                    self.assertIsNone(mirror.public_identity('https://cos.example/asset'))
                else:
                    with self.assertRaises(urllib.error.HTTPError):
                        mirror.public_identity('https://cos.example/asset')
                self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertEqual(opener.return_value.open.call_args.args[0].get_method(), 'HEAD')

    def test_redirect_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'Redirect refused'):
            mirror.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.example/asset')

    def test_github_prior_manifest_is_verified_in_memory_and_never_read_from_bucket(self):
        payload = {'version': '1.0.2', 'releaseId': 'lees-pdf-v1.0.2'}
        calls = ['[{"tagName":"lees-pdf-v1.0.1"},{"tagName":"lees-mail-v9.0.0"},{"tagName":"lees-pdf-v1.0.2"}]', '{"release":{}}']
        with patch.object(mirror.subprocess, 'check_output', side_effect=calls) as command, \
             patch.object(mirror, 'verified_manifest', return_value={'payload': payload}) as verify, \
             patch.object(mirror.urllib.request, 'build_opener') as bucket, \
             patch.object(Path, 'write_bytes') as write:
            self.assertEqual(mirror.github_previous_manifest()[1]['payload'], payload)
            self.assertIn('lees-pdf-v1.0.2', command.call_args.args[0])
            self.assertEqual(command.call_args.args[0][-2:], ['--output', '-'])
            verify.assert_called_once_with(raw='{"release":{}}')
            bucket.assert_not_called()
            write.assert_not_called()

    def test_cos_single_put_sends_the_local_content_checksum(self):
        import base64
        # Synthetic file interface keeps the test free of real storage or credentials.
        file = MagicMock()
        file.open.return_value.__enter__.return_value = MagicMock()
        expected = ('a' * 32, 123)
        sdk = MagicMock()
        with patch.dict('sys.modules', {'qcloud_cos': sdk}), \
             patch.dict(mirror.os.environ, {'COS_PUBLIC_BASE_URL': 'https://cos.example/',
                        'TENCENT_COS_REGION': 'test', 'TENCENT_COS_SECRET_ID': 'synthetic',
                        'TENCENT_COS_SECRET_KEY': 'synthetic', 'TENCENT_COS_BUCKET': 'test'}), \
             patch.object(mirror, 'file_identity', return_value=expected), \
             patch.object(mirror, 'public_identity', side_effect=[None, expected]):
            mirror.put('cos', 'lees-pdf/releases/1.0.0/test.exe', file)
            options = sdk.CosS3Client.return_value.put_object.call_args.kwargs
            self.assertEqual(options['ContentLength'], '123')
            self.assertEqual(options['ContentMD5'], base64.b64encode(bytes.fromhex(expected[0])).decode('ascii'))
            sdk.CosS3Client.return_value.upload_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
