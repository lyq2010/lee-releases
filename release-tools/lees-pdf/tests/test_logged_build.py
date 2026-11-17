import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SPEC = importlib.util.spec_from_file_location("logged_build", Path(__file__).resolve().parents[1] / "logged_build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class LoggedBuildTests(unittest.TestCase):
    def invoke(self, source, **options):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "private.log"
            progress = io.StringIO()
            with contextlib.redirect_stdout(progress), mock.patch.object(
                    BUILD, "process_activity", create=True, side_effect=options.pop("samples", lambda _: None)):
                code = BUILD.run([sys.executable, "-u", "-c", source], log, "windows",
                                 interval=0.05, **options)
            return code, log.read_text(), progress.getvalue()

    def test_private_output_stays_in_log_and_child_exit_is_preserved(self):
        code, log, progress = self.invoke("print('private-token'); print('Compiling dependency'); raise SystemExit(7)")
        self.assertEqual(code, 7)
        self.assertIn("private-token", log)
        self.assertNotIn("private-token", progress)
        self.assertIn("compiledUnits=1", progress)
        self.assertIn("failed-7", progress)

    def test_known_phase_and_argument_boundaries(self):
        code, log, progress = self.invoke("print('LEES_BUILD_PHASE:licenses'); print('LEES_BUILD_PHASE:secret')")
        self.assertEqual(code, 0)
        self.assertIn("phase=licenses", progress)
        self.assertNotIn("secret", progress)

    def test_quiet_child_is_stopped(self):
        code, _, progress = self.invoke("import time; time.sleep(10)", quiet_timeout=0.15)
        self.assertEqual(code, 124)
        self.assertIn("timeout", progress)

    def test_output_does_not_defeat_total_timeout(self):
        code, log, _ = self.invoke("import time\nwhile True: print('tick'); time.sleep(.01)", timeout=0.15)
        self.assertEqual(code, 124)
        self.assertIn("tick", log)

    def test_silent_busy_child_survives_quiet_timeout(self):
        ticks = iter(range(1000))
        code, _, progress = self.invoke(
            "import time; time.sleep(.5)", quiet_timeout=0.15,
            samples=lambda _: {42: (next(ticks), 1024, "compiler", "ui")})
        self.assertEqual(code, 0)
        self.assertIn("active=compiler/ui", progress)

    def test_replaced_child_cpu_does_not_look_idle(self):
        ticks = iter(range(1000))
        code, _, _ = self.invoke(
            "import time; time.sleep(.5)", quiet_timeout=0.15,
            samples=lambda _: {next(ticks): (1, 1024, "compiler", "ui")})
        self.assertEqual(code, 0)

    def test_cpu_activity_does_not_defeat_total_timeout(self):
        ticks = iter(range(1000))
        code, _, progress = self.invoke(
            "import time; time.sleep(10)", timeout=0.2,
            samples=lambda _: {42: (next(ticks), 1024, "compiler", "ui")})
        self.assertEqual(code, 124)
        self.assertIn("reason=total-timeout", progress)

    def test_compiler_failure_exposes_only_error_codes(self):
        code, _, progress = self.invoke("print('error[E0308]: private source details'); raise SystemExit(1)")
        self.assertEqual(code, 1)
        self.assertIn("compilerCodes=E0308", progress)
        self.assertNotIn("private source details", progress)


    def test_public_orchestrator_location_without_private_output(self):
        code, _, progress = self.invoke(
            "print(r'C:\\runner\\release-tools\\lees-pdf\\build.ps1:93 private details'); raise SystemExit(1)")
        self.assertEqual(code, 1)
        self.assertIn("orchestratorLine=93", progress)
        self.assertNotIn("private details", progress)
        self.assertNotIn("runner", progress)

    def test_repeated_phase_and_output_do_not_defeat_phase_deadline(self):
        with mock.patch.dict(BUILD.PHASE_TIMEOUTS, {"certificate": 0.15}):
            code, _, progress = self.invoke(
                "import time\nwhile True: print('LEES_BUILD_PHASE:certificate'); time.sleep(.01)")
        self.assertEqual(code, 124)
        self.assertIn("reason=phase-timeout", progress)

    def test_only_bounded_compiler_budget_is_public(self):
        code, _, progress = self.invoke("print('LEES_BUILD_JOBS:4'); print('LEES_BUILD_JOBS:99 private')")
        self.assertEqual(code, 0)
        self.assertIn("compilerJobs=4", progress)
        self.assertNotIn("99", progress)
        self.assertNotIn("private", progress)

if __name__ == "__main__":
    unittest.main()
