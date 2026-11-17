import unittest
from unittest import mock

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_activity as ACTIVITY


class BuildActivityTests(unittest.TestCase):
    def test_cpu_clock_formats(self):
        self.assertEqual(ACTIVITY.cpu_seconds("12:34.50"), 754.5)
        self.assertEqual(ACTIVITY.cpu_seconds("01:02:03"), 3723)
        self.assertEqual(ACTIVITY.cpu_seconds("2-01:02:03"), 176523)

    def test_only_owned_descendants_and_safe_labels(self):
        rows = [(42, 1, 1, 1024, 'pwsh private-password'),
                (43, 42, 2, 2048, '/private/tool/rustc --crate-name lees_pdf_native_ui secret'),
                (44, 43, 3, 4096, '/usr/bin/ld secret'),
                (99, 1, 100, 99999, '/usr/bin/rustc --crate-name private_secret')]
        snapshot = ACTIVITY.descendants(rows, 42)
        self.assertEqual(set(snapshot), {42, 43, 44})
        self.assertEqual(snapshot[43], (2, 2048, 'compiler', 'ui'))
        self.assertEqual(snapshot[44][2], 'linker')
        self.assertNotIn('secret', repr(snapshot))

    def test_macos_ps_sampling(self):
        result = mock.Mock(stdout='42 1 00:01.50 1024 /bin/pwsh private\n43 42 00:02.00 2048 /bin/rustc --crate-name lees_pdf_native_ui\n')
        with mock.patch.object(ACTIVITY.os, 'name', 'posix'), mock.patch.object(
                ACTIVITY.subprocess, 'run', return_value=result):
            snapshot = ACTIVITY.process_activity(42)
        self.assertEqual(snapshot[43], (2, 2048 * 1024, 'compiler', 'ui'))


if __name__ == '__main__':
    unittest.main()
