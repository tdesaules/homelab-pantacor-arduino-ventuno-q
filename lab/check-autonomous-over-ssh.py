#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from diagnostic_ssh import ROOT
from persistent_session import exercise_autonomous

parser = argparse.ArgumentParser(description='Validate direct persistent Pantavisor reboot/update/rollback, then return to Ubuntu')
parser.add_argument('--install-id', required=True)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-autonomous')
args = parser.parse_args()
assert re.fullmatch('[0-9a-f]{32}', args.install_id)
directory = ROOT / 'artifacts/autonomous' / args.install_id
inputs = json.loads((directory / 'build-inputs.json').read_text())
assert inputs['autonomous_boot']
record = json.loads((directory / 'installed.json').read_text())
exercise_autonomous('192.168.1.20', 2222, directory, inputs, args.output_dir, args.install_id,
                    expected_identity=record['previous_application_identity'], previous_starts=record['previous_application_starts'], require_watchdog=True)
