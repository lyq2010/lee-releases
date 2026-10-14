import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('retention', Path(__file__).resolve().parents[1] / 'retention.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class RetentionTests(unittest.TestCase):
    def test_only_previous_pdf_version_is_selected(self):
        keys = ['lees-pdf/releases/0.1.0/lees-pdf-0.1.0-windows-x86_64-setup.exe',
                'lees-pdf/releases/0.1.0/SHA256SUMS',
                'lees-pdf/releases/0.1.1/release-manifest.json',
                'latest-lees-pdf.json', 'LeesEmby_1.0.0_x64-setup.exe',
                'lees-mail/releases/0.1.0/LeesMail.exe']
        self.assertEqual(retention.old_assets(keys, '0.1.1'), sorted(keys[:2]))

    def test_cos_prefix_is_exact(self):
        selected = 'releases/lees-pdf/releases/0.1.0/SHA256SUMS'
        self.assertEqual(retention.old_assets([selected, 'other/lees-pdf/releases/0.1.0/SHA256SUMS'], '0.1.1', 'releases'), [selected])

    def test_newer_release_stops_cleanup(self):
        with self.assertRaises(RuntimeError):
            retention.old_assets(['lees-pdf/releases/0.2.0/SHA256SUMS'], '0.1.1')

    def test_unknown_and_traversal_keys_stop_cleanup(self):
        for key in ['lees-pdf/releases/0.1.0/user.pdf', 'lees-pdf/releases/../SHA256SUMS', 'lees-pdf/releases/0.1.0/sub/lees-pdf-package.exe']:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                retention.old_assets([key], '0.1.1')

    def test_cos_pagination_preserves_the_pdf_prefix(self):
        calls = []
        class Client:
            def list_objects(self, **arguments):
                calls.append(arguments)
                if arguments['Marker'] == '':
                    return {'Contents': [{'Key': 'a'}], 'IsTruncated': True, 'NextMarker': 'next'}
                return {'Contents': [{'Key': 'b'}], 'IsTruncated': False}
        self.assertEqual(retention.cos_keys(Client(), 'bucket', 'lees-pdf/releases/'), ['a', 'b'])
        self.assertTrue(all(call['Prefix'] == 'lees-pdf/releases/' for call in calls))

    def test_invalid_cos_cursor_stops_cleanup(self):
        class Client:
            def list_objects(self, **arguments):
                return {'IsTruncated': True}
        with self.assertRaises(RuntimeError):
            retention.cos_keys(Client(), 'bucket', 'lees-pdf/releases/')


if __name__ == '__main__':
    unittest.main()
