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

PHASES = {"preflight", "certificate", "fetch", "tools", "inputs", "application", "engines", "fonts", "licenses", "installer",
          "signing", "verification", "metadata"}
LOG_LIMIT = 64 * 1024 * 1024


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
    started = activity = last_report = time.monotonic()
    size = units = 0
    errors = set()
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
                  f"component={component} reason={reason} compilerCodes={','.join(sorted(errors)) or 'none'}{resource}",
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
                reason = "total-timeout" if now - started >= timeout else "idle-timeout"
                if now - started >= timeout or now - activity >= quiet_timeout:
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
                    errors.update(re.findall(r"\berror\[(E[0-9]{4})\]", line))
                    if line.startswith("LEES_BUILD_PHASE:") and line[17:] in PHASES:
                        phase = line[17:]
                        report("running")
                    if line.startswith("Compiling ") or line.startswith("Finished "):
                        units += 1
                        name = line.split()[1] if line.startswith("Compiling ") else ""
                        component = {"lees-pdf-native-ui":"ui", "lees-pdf-native":"host",
                                     "lees-reader-core":"pdf-core", "lees-ocr-engine":"ocr",
                                     "lees-scan-engine":"scan"}.get(name, "dependencies")
            code = process.wait(timeout=max(1, timeout - (time.monotonic() - started)))
            report("success" if code == 0 else f"failed-{code}")
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
