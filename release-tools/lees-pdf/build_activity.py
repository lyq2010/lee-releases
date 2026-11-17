"""Sample only the build's descendants; expose roles and approved component labels."""
import json
import os
from pathlib import Path
import re
import subprocess

COMPONENTS = {"lees_pdf_native_ui": "ui", "lees_pdf_native": "host",
              "lees_reader_core": "pdf-core", "lees_ocr_engine": "ocr",
              "lees_scan_engine": "scan"}


def labels(command):
    name = Path(command.split('"')[1] if command.startswith('"') else command.split()[0]).name.lower()
    role = {"rustc": "compiler", "rustc.exe": "compiler", "cargo": "cargo",
            "cargo.exe": "cargo", "clang": "compiler", "clang.exe": "compiler",
            "clang++": "compiler", "cl.exe": "compiler", "link.exe": "linker",
            "ld": "linker", "lld-link.exe": "linker", "cmake": "cmake",
            "cmake.exe": "cmake"}.get(name, "worker")
    crate = re.search(r"(?:^|\s)--crate-name\s+([a-zA-Z0-9_]+)(?:\s|$)", command)
    return role, COMPONENTS.get(crate[1], "dependencies") if crate else "dependencies"


def cpu_seconds(value):
    days, _, clock = value.rpartition("-")
    parts = clock.split(":")
    if len(parts) not in (2, 3):
        raise ValueError("Invalid process CPU clock")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds + (int(days) * 86400 if days else 0)


def descendants(rows, pid):
    selected = {pid}
    while True:
        added = {child for child, parent, *_ in rows if parent in selected} - selected
        if not added:
            break
        selected.update(added)
    return {child: (cpu, memory, *labels(command))
            for child, _, cpu, memory, command in rows if child in selected}


def process_activity(pid):
    try:
        if os.name == "nt":
            script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
                      "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
                      "KernelModeTime,UserModeTime,WorkingSetSize,Name,CommandLine | ConvertTo-Json -Compress")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                    capture_output=True, timeout=10, check=True, encoding="utf-8")
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            rows = [(int(r["ProcessId"]), int(r["ParentProcessId"]),
                     (int(r["KernelModeTime"] or 0) + int(r["UserModeTime"] or 0)) / 10000000,
                     int(r["WorkingSetSize"] or 0), r["CommandLine"] or r["Name"]) for r in data]
        else:
            result = subprocess.run(["ps", "-axo", "pid=,ppid=,time=,rss=,args="],
                                    capture_output=True, timeout=10, check=True, encoding="utf-8")
            rows = []
            for line in result.stdout.splitlines():
                child, parent, cpu, memory, command = line.split(None, 4)
                rows.append((int(child), int(parent), cpu_seconds(cpu), int(memory) * 1024, command))
        return descendants(rows, pid)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError):
        return None
