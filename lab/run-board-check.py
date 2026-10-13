#!/usr/bin/env python3
"""Run a shell script over verified SSH and retain its complete output locally."""
import argparse
import datetime
import os
import re
import shlex
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('script', type=Path)
parser.add_argument('--host', default='arduino@192.168.1.20')
parser.add_argument('--sudo', action='store_true', help='Authenticate sudo via SSH stdin')
parser.add_argument('--argument', action='append', default=[], help='Argument passed to the remote shell script (repeatable)')
parser.add_argument('--allow-nvme-scratch', action='store_true', help='Allow the bounded NVMe write/restore test')
args = parser.parse_args()
env = os.environ | {
    'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'),
    'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': os.environ.get('DISPLAY', ':0'),
}
payload = args.script.read_bytes()
if args.allow_nvme_scratch:
    payload = b'export PV_ALLOW_NVME_SCRATCH=yes\n' + payload
remote = 'bash -s'
if args.sudo:
    text = (root / 'docs/access.local.md').read_text()
    password = re.search(r'Mot de passe : `([^`]+)`', text).group(1)
    payload = password.encode() + b'\n' + payload
    remote = "sudo -S -p '' bash -s"
remote += ' -- ' + shlex.join(args.argument)
result = subprocess.run([
    'ssh', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
    '-o', 'ConnectTimeout=10', '-o', 'NumberOfPasswordPrompts=1',
    args.host, remote,
], input=payload, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, env=env, timeout=600)
output = root / 'artifacts'
output.mkdir(exist_ok=True)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
log = output / f'{stamp}-{args.script.stem}.log'
log.write_bytes(result.stdout)
print(result.stdout.decode(errors='replace'))
print(f'Log: {log}; SSH exit status: {result.returncode}')
raise SystemExit(result.returncode)
