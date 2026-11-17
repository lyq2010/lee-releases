import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NsisToolTests(unittest.TestCase):
    def test_actual_distribution_layout_selects_canonical_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / 'nsis-3.11/makensis.exe'
            secondary = root / 'nsis-3.11/Bin/makensis.exe'
            secondary.parent.mkdir(parents=True)
            canonical.write_bytes(b'synthetic compiler, not executed')
            secondary.write_bytes(b'synthetic secondary compiler, not executed')
            result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command',
                                     '& { param($helper,$folder) . $helper; Get-NsisCompiler $folder }',
                                     str(ROOT / 'build-tools.ps1'), str(root)],
                                    capture_output=True, text=True, encoding='utf-8', timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), canonical)

    def test_missing_canonical_compiler_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secondary = root / 'nsis-3.11/Bin/makensis.exe'
            secondary.parent.mkdir(parents=True)
            secondary.write_bytes(b'synthetic secondary compiler, not executed')
            result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command',
                                     '& { param($helper,$folder) $ErrorActionPreference="Stop"; . $helper; Get-NsisCompiler $folder }',
                                     str(ROOT / 'build-tools.ps1'), str(root)],
                                    capture_output=True, text=True, encoding='utf-8', timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('固定 NSIS 发行入口缺失', result.stderr)