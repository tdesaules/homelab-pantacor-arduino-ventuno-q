#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Fetch the installation receipt without changing the board')
parser.add_argument('--install-id', required=True)
args = parser.parse_args()
assert re.fullmatch('[0-9a-f]{32}', args.install_id)
directory = root / 'artifacts/autonomous' / args.install_id
env = os.environ | {'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
subprocess.run(['scp', '-q', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
                'arduino@192.168.1.20:/home/arduino/.cache/ventuno-autonomous-' + args.install_id + '/installed.json',
                str(directory / 'installed.json')], env=env, check=True)
print(directory / 'installed.json')
