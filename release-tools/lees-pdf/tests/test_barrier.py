import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BARRIER = Path(__file__).resolve().parents[1] / 'barrier.mjs'


class BarrierTests(unittest.TestCase):
    def run_barrier(self, **r2_changes):
        with tempfile.TemporaryDirectory(prefix='lees-pdf-readiness-') as directory:
            for source in ('cos', 'r2'):
                row = {'source': source, 'verified': True, 'version': '0.1.0', 'payloadSha256': 'a' * 64, 'runId': '42'}
                if source == 'r2':
                    row.update(r2_changes)
                (Path(directory) / f'readiness-{source}.json').write_text(json.dumps(row), encoding='utf-8')
            return subprocess.run(['node', str(BARRIER), directory], env={**os.environ, 'GITHUB_RUN_ID': '42'}, capture_output=True, timeout=10).returncode

    def test_current_matching_mirrors_pass(self):
        self.assertEqual(self.run_barrier(), 0)

    def test_previous_batch_cannot_overwrite_current_readiness(self):
        self.assertNotEqual(self.run_barrier(runId='41'), 0)

    def test_mismatched_content_and_version_are_rejected(self):
        self.assertNotEqual(self.run_barrier(payloadSha256='b' * 64), 0)
        self.assertNotEqual(self.run_barrier(version='0.1.1'), 0)

    def test_unverified_mirror_is_rejected(self):
        self.assertNotEqual(self.run_barrier(verified=False), 0)


if __name__ == '__main__':
    unittest.main()
