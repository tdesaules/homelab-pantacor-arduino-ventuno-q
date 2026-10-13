#!/usr/bin/env python3
"""Run the long integration test in the background, keeping a failed guest inspectable."""
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / 'artifacts/prototype-1084-k0s'
log = directory / ('test-' + uuid.uuid4().hex + '.log')
with log.open('wb') as stream:
    process = subprocess.Popen([sys.executable, str(ROOT / 'lab/test-autonomous-boot.py'),
        '--output-dir', str(directory), '--default-boot', '--keep-on-failure'],
        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
print('TEST_PID=' + str(process.pid))
print('LOG=' + str(log))
