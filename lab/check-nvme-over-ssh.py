#!/usr/bin/env python3
"""Check NVMe persistence without restarting either container during the trial."""
import argparse
import json
import re
import subprocess
import time
from diagnostic_ssh import ROOT, ssh_command
from nvme_validation import validate_nvme

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--trial-id', required=True)
parser.add_argument('--expected-starts', type=int, required=True)
parser.add_argument('--previous-trial', help='Require the persistent identity recorded by the previous boot')
args = parser.parse_args()
assert re.fullmatch('[0-9a-f]{32}', args.trial_id)
directory = ROOT / 'artifacts/trials' / args.trial_id
inputs = json.loads((directory / 'build-inputs.json').read_text())
identity = None
if args.previous_trial:
    assert re.fullmatch('[0-9a-f]{32}', args.previous_trial)
    identity = json.loads((ROOT / 'artifacts/trials' / args.previous_trial / 'nvme-check.json').read_text())['application_identity']
for _ in range(25):
    reply = subprocess.run(ssh_command('192.168.1.20', command='cat /proc/cmdline; ventuno-revision-status'), capture_output=True, text=True, timeout=15)
    (directory / 'nvme-status.log').write_text(reply.stdout + reply.stderr)
    try:
        if reply.returncode or 'ventuno_trial=' + args.trial_id not in reply.stdout:
            raise ValueError('SSH or trial identity check failed')
        result = validate_nvme(reply.stdout, inputs, args.expected_starts, identity)
        if result['device'] != '/dev/nvme0n1p1': raise ValueError('Unexpected hardware NVMe device')
        break
    except (ValueError, KeyError, IndexError):
        time.sleep(1)
else:
    raise SystemExit('NVMe validation failed; inspect nvme-status.log')
(directory / 'nvme-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
print('PASS: NVMe-backed application data, expected counter and persistent identity')
