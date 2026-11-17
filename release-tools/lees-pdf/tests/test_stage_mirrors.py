import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('stage_mirrors', Path(__file__).resolve().parents[1] / 'stage_mirrors.py')
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)


class MirrorStageTests(unittest.TestCase):
    def test_both_mirrors_start_concurrently_and_only_success_uploads_receipt(self):
        for failed in (None, 'cos', 'r2'):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                for source in ('cos', 'r2'):
                    (folder / f'readiness-{source}.json').write_text('stale fixture', encoding='utf-8')
                barrier = threading.Barrier(2)
                uploaded = []

                def command(args, **options):
                    source = options['env']['MIRROR']
                    if args[0] == sys.executable:
                        barrier.wait(timeout=5)
                        return SimpleNamespace(returncode=1 if source == failed else 0)
                    uploaded.append(source)
                    return SimpleNamespace(returncode=0)

                with mock.patch.object(STAGE.subprocess, 'run', side_effect=command), contextlib.redirect_stdout(io.StringIO()):
                    code = STAGE.stage(folder, 'lees-pdf-v1.0.1')
                self.assertEqual(code, 1 if failed else 0)
                self.assertEqual(set(uploaded), {'cos', 'r2'} - ({failed} if failed else set()))

    def test_invalid_tag_fails_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(STAGE.subprocess, 'run') as command:
            with self.assertRaises(RuntimeError):
                STAGE.stage(Path(directory), '--repo=untrusted')
            command.assert_not_called()
