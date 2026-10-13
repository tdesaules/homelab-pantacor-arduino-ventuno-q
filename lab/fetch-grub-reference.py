#!/usr/bin/env python3
"""Capture the board's existing ARM64 GRUB EFI loader for the autonomous QEMU test."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / 'lab/run-board-check.py'), '--sudo',
                str(root / 'lab/export-grub-reference.sh')], check=True)
directory = root / 'artifacts/grub-reference'
directory.mkdir(exist_ok=True)
env = os.environ | {'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
for name in ('grubaa64.efi', 'arm64-efi.tar.gz', 'reference.json'):
    subprocess.run(['scp', '-q', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
                    'arduino@192.168.1.20:/home/arduino/.cache/ventuno-grub-reference/' + name,
                    str(directory / name)], env=env, check=True)
record = json.loads((directory / 'reference.json').read_text())
assert hashlib.sha256((directory / 'grubaa64.efi').read_bytes()).hexdigest() == record['sha256']
assert hashlib.sha256((directory / 'arm64-efi.tar.gz').read_bytes()).hexdigest() == record['modules_sha256']
print('Verified ARM64 GRUB reference:', directory)
