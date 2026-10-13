#!/usr/bin/env python3
"""Exercise local updates, or verify recovery using the same saved runtime store."""
import argparse
import json
from pathlib import Path
import re
from diagnostic_ssh import ROOT
from local_updates import Session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--trial-id', required=True)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-updates')
phase = parser.add_mutually_exclusive_group()
phase.add_argument('--recover-from', help='Scenario record trial used to verify recovery of the committed revision')
phase.add_argument('--commit-from', help='Verify the updated revision commits, then trigger the unready revision')
phase.add_argument('--finish-prepared', action='store_true', help='Finish a prepared v2 transition using the recorded initial/v2/v1 proofs')
parser.add_argument('--previous-nvme-trial', help='Require the NVMe identity recorded before these updates')
args = parser.parse_args()
assert re.fullmatch('[0-9a-f]{32}', args.trial_id)
directory = ROOT / 'artifacts/trials' / args.trial_id
inputs = json.loads((directory / 'build-inputs.json').read_text())
session = Session('192.168.1.20', 2222, directory)
if args.finish_prepared:
    assert 'ventuno_trial=' + args.trial_id in session.run('cat /proc/cmdline')
    session.finish_prepared(inputs, args.output_dir)
elif args.recover_from or args.commit_from:
    prior = args.recover_from or args.commit_from
    assert re.fullmatch('[0-9a-f]{32}', prior)
    previous = json.loads((ROOT / 'artifacts/trials' / prior / 'updates-result.json').read_text())
    assert 'ventuno_trial=' + args.trial_id in session.run('cat /proc/cmdline')
    if args.commit_from:
        session.fail_after_commit(inputs, previous)
    else:
        session.wait_ready('rollback-recovered', inputs, previous['last_good_revision'], '2.0.0', previous['expected_after_rollback_boot'], previous['application_identity'], core_starts=3, require_done=True)
        progress = json.loads(session.control('steps', 'show-progress', previous['failed_revision']))
        assert progress['status'] == 'ERROR' and 'goal' in progress['status-msg'].lower(), progress
        (directory / 'failed-update-progress.json').write_text(json.dumps(progress, indent=2) + '\n')
        session.shells(inputs)
        print('PASS: committed revision restored after failed update; NVMe identity/counter and shells preserved')
else:
    identity = None
    if args.previous_nvme_trial:
        assert re.fullmatch('[0-9a-f]{32}', args.previous_nvme_trial)
        identity = json.loads((ROOT / 'artifacts/trials' / args.previous_nvme_trial / 'nvme-check.json').read_text())['application_identity']
    session.exercise(inputs, args.output_dir, args.trial_id, identity)
