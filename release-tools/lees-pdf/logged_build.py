"""Keep private build output local while publishing bounded, non-sensitive progress."""
import argparse
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

from build_activity import process_activity

PHASES = {"preflight", "certificate", "fetch", "tools", "nsis", "clang", "inputs", "application", "engines", "fonts", "licenses", "installer",
          "signing", "verification", "metadata"}
LOG_LIMIT = 64 * 1024 * 1024
PHASE_TIMEOUTS = {"preflight": 300, "certificate": 120, "fetch": 900, "tools": 900,
                  "nsis": 900, "clang": 120, "inputs": 900, "licenses": 900,
                  "installer": 900, "signing": 900, "verification": 900, "metadata": 300}

INPUT_TRACE = re.compile(r'^File "[^"]*[/\\](prepare-native-(?:macos|windows|assets|reader)\.py)", line ([0-9]{1,4}),')
INPUT_ERROR = re.compile(r'^(?:[A-Za-z_]+\.)*(HTTPError|URLError|TimeoutError|SSLError|IncompleteRead|RemoteDisconnected|CalledProcessError|FileNotFoundError|ValueError|BadZipFile|PermissionError|OSError):')
HTTP_STATUS = re.compile(r'HTTP Error ([45][0-9]{2})\b')


def stop(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=30)


def run(command, log, phase, timeout=10800, quiet_timeout=2700, interval=30):
    started = activity = last_report = phase_started = time.monotonic()
    size = units = 0
    errors = set()
    orchestrator_line = 0
    input_trace, input_errors, http_codes = set(), set(), set()
    compiler_jobs = 0
    component = "dependencies"
    messages = queue.Queue(maxsize=64)
    stopped = threading.Event()
    options = {"start_new_session": True} if os.name != "nt" else {}
    with log.open("ab") as output:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, **options)

        def enqueue(block):
            while not stopped.is_set():
                try:
                    messages.put(block, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def read():
            try:
                while block := process.stdout.readline(65536):
                    enqueue(block)
            finally:
                process.stdout.close()
                enqueue(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        previous_cpu = {}
        cpu_total = 0.0
        resource = ""

        def sample():
            nonlocal previous_cpu, cpu_total, activity, resource
            metrics = process_activity(process.pid)
            resource = " metrics=unavailable"
            if metrics is not None:
                # Track each PID separately: completed rustc children must not mask new work.
                deltas = {pid: max(0, values[0] - previous_cpu.get(pid, 0)) for pid, values in metrics.items()}
                delta = sum(deltas.values())
                cpu_total += delta
                if delta > 0.01:
                    activity = time.monotonic()
                previous_cpu = {pid: values[0] for pid, values in metrics.items()}
                memory = sum(values[1] for values in metrics.values()) // (1024 * 1024)
                active = max(deltas, key=deltas.get) if deltas else None
                role, target = metrics[active][2:] if active is not None else ("none", "none")
                resource = (f" cpuSeconds={cpu_total:.2f} cpuDelta={delta:.2f} residentMiB={memory} "
                            f"processes={len(metrics)} active={role}/{target}")

        def report(state, reason="none"):
            print(f"native-build phase={phase} state={state} elapsed={int(time.monotonic()-started)}s "
                  f"quiet={int(time.monotonic()-activity)}s logBytes={size} compiledUnits={units} "
                  f"component={component} compilerJobs={compiler_jobs} reason={reason} orchestratorLine={orchestrator_line} compilerCodes={','.join(sorted(errors)) or 'none'}{resource}",
                  flush=True)

        try:
            sample()
            report("running")
            complete = False
            while not complete:
                now = time.monotonic()
                if now - last_report >= interval or now - activity >= quiet_timeout:
                    sample()
                    last_report = time.monotonic()
                    report("running")
                now = time.monotonic()
                phase_expired = now - phase_started >= PHASE_TIMEOUTS.get(phase, timeout)
                reason = ("total-timeout" if now - started >= timeout else
                          "phase-timeout" if phase_expired else "idle-timeout")
                if now - started >= timeout or phase_expired or now - activity >= quiet_timeout:
                    report("timeout", reason)
                    stop(process)
                    return 124
                try:
                    block = messages.get(timeout=min(interval, 0.25))
                except queue.Empty:
                    block = b""
                if block is None:
                    complete = True
                elif block:
                    activity = time.monotonic()
                    size += len(block)
                    if size > LOG_LIMIT:
                        report("log-limit")
                        stop(process)
                        return 125
                    output.write(block)
                    output.flush()
                    line = block.decode("utf-8", errors="replace").strip()
                    if re.fullmatch(r"LEES_BUILD_JOBS:[1-4]", line):
                        compiler_jobs = int(line[-1])
                        report("running")
                    errors.update(re.findall(r"\berror\[(E[0-9]{4})\]", line))
                    location = re.search(r"/release-tools/lees-pdf/build\.ps1:([0-9]+)", line.replace("\\", "/"))
                    if location:
                        orchestrator_line = int(location[1])
                    if line.startswith("LEES_BUILD_PHASE:") and line[17:] in PHASES:
                        if phase != line[17:]:
                            phase_started = time.monotonic()
                        phase = line[17:]
                        report("running")
                    if phase == "inputs":
                        if frame := INPUT_TRACE.match(line):
                            input_trace.add(f"{frame[1]}:{frame[2]}")
                        if failure := INPUT_ERROR.match(line):
                            input_errors.add(failure[1])
                        if status := HTTP_STATUS.search(line):
                            http_codes.add(status[1])
                    if line.startswith("Compiling ") or line.startswith("Finished "):
                        units += 1
                        name = line.split()[1] if line.startswith("Compiling ") else ""
                        component = {"lees-pdf-native-ui":"ui", "lees-pdf-native":"host",
                                     "lees-reader-core":"pdf-core", "lees-ocr-engine":"ocr",
                                     "lees-scan-engine":"scan"}.get(name, "dependencies")
            code = process.wait(timeout=max(1, timeout - (time.monotonic() - started)))
            report("success" if code == 0 else f"failed-{code}")
            if code != 0 and phase == "inputs":
                print("native-input-diagnostics "
                      f"trace={','.join(sorted(input_trace)) or 'none'} "
                      f"categories={','.join(sorted(input_errors)) or 'none'} "
                      f"http={','.join(sorted(http_codes)) or 'none'}", flush=True)
            return code
        except BaseException:
            stop(process)
            raise
        finally:
            stopped.set()
            reader.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--phase", choices=["preflight", "fetch", "tools", "windows", "macos"], required=True)
    parser.add_argument("--timeout", type=int, default=10800)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.timeout <= 0:
        parser.error("A command and positive timeout are required")
    sys.exit(run(command, args.log, args.phase, timeout=args.timeout))
