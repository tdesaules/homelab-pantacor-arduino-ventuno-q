#!/usr/bin/env python3
"""Wait for authenticated diagnostic SSH and verify the expected trial marker."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import time
from diagnostic_ssh import KEYS, ROOT, ssh_command

profile = json.loads((KEYS / 'network-profile.json').read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', default=profile['expected_ipv4'])
parser.add_argument('--port', type=int, default=profile['ssh_port'])
parser.add_argument('--trial-id', required=True)
parser.add_argument('--timeout', type=int, default=150)
parser.add_argument('--revision-network', action='store_true')
parser.add_argument('--core', action='store_true')
args = parser.parse_args()
assert re.fullmatch('[0-9a-f]{32}', args.trial_id)
start = time.monotonic()
last = ''
while time.monotonic() - start < args.timeout:
    try:
        result = subprocess.run(ssh_command(args.host, args.port), capture_output=True, text=True, timeout=12)
        last = result.stdout + result.stderr
        if result.returncode == 0:
            assert 'SSH_DIAGNOSTIC_OK' in result.stdout
            if args.revision_network or args.core:
                label = 'core' if args.core else 'revision'
                test = 'test -f /etc/ventuno-core-release && ' if args.core else ''
                owner = subprocess.run(ssh_command(args.host, args.port, command=test + 'test -f /etc/ventuno-revision-network && test ! -f /etc/ventuno-embedded.config && echo NETWORK_OWNER=' + label), capture_output=True, text=True, timeout=12)
                assert owner.returncode == 0 and 'NETWORK_OWNER=' + label in owner.stdout
                last += owner.stdout
            else:
                assert 'ventuno-init' in result.stdout
            assert 'ventuno_trial=' + args.trial_id in result.stdout
            assert 'DHCP_BOUND=1' in result.stdout
            directory = ROOT / 'artifacts/trials' / args.trial_id
            directory.mkdir(parents=True, exist_ok=True)
            text = f'Host verification time: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n' + last
            (directory / 'ssh-check.log').write_text(text)
            print(text)
            print(f'PASS: authenticated SSH after {time.monotonic()-start:.1f}s; host key verified')
            break
    except subprocess.TimeoutExpired:
        last = 'SSH command timed out'
    time.sleep(2)
else:
    print(last)
    raise SystemExit('Diagnostic SSH did not become available within the timeout')
