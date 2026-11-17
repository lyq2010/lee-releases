"""Stage both mirrors from one verified local asset set; preserve independent outcomes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def stage_one(source, folder, tag):
    environment = os.environ | {'MIRROR': source}
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('mirror.py')), 'stage', str(folder)],
                                env=environment, timeout=1800)
        if result.returncode:
            return result.returncode
        receipt = folder / f'readiness-{source}.json'
        if not receipt.is_file():
            raise RuntimeError(f'Missing successful {source} readiness receipt')
        return subprocess.run(['gh', 'release', 'upload', tag, str(receipt), '--repo',
                               'lyq2010/lee-releases', '--clobber'], env=environment, timeout=300).returncode
    except subprocess.TimeoutExpired:
        return 124


def stage(folder, tag):
    if not folder.is_dir() or not re.fullmatch(r'lees-pdf-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag):
        raise RuntimeError('Invalid mirror staging directory or release tag')
    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(stage_one, source, folder, tag): source for source in ('cos', 'r2')}
        for job in as_completed(jobs):
            source = jobs[job]
            results[source] = job.result()
            print(json.dumps({'mirror': source, 'exitCode': results[source]}), flush=True)
    return 1 if any(results.values()) else 0


if __name__ == '__main__':
    raise SystemExit(stage(Path(sys.argv[1]).resolve(), os.environ['PUBLIC_TAG']))
