#!/usr/bin/env python3
"""Check the deployed core clients without changing Kubernetes workloads or rebooting."""
import json
import argparse
from pathlib import Path
import subprocess
import time
import uuid
from local_updates import Session
from management_tools_session import exercise_management_tools
from persistent_session import wait_boot

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='locals/k0s-os-070')
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-k0s-os')
args = parser.parse_args()
directory = ROOT / 'artifacts/management-tools' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, directory)
wait_boot(session, '6491b61ba229489cb8bacb1719de7c2c', timeout=240)
until = time.monotonic() + 180
while time.monotonic() < until:
    try:
        progress = json.loads(session.control('steps', 'show-progress', 'current'))
        revision = session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')
        nodes = json.loads(session.run('kubectl get nodes -o json --request-timeout=15s'))
        if revision == args.revision and progress['status'] == 'DONE' and any(
            any(c['type'] == 'Ready' and c['status'] == 'True' for c in n['status']['conditions']) for n in nodes['items']): break
    except (RuntimeError, subprocess.TimeoutExpired): pass
    time.sleep(3)
else: raise RuntimeError('Core clients/cluster did not become ready')
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
assert session.run('cat /sys/fs/cgroup/memory.max').strip() == '536870912'
session.shells(inputs)
exercise_management_tools(session)
session.snapshot('core-tools-active')
(directory / 'nodes.json').write_text(json.dumps(nodes, indent=2) + '\n')
print('PASS: management clients deployed; cluster and SSH remain available. Logs:', directory)
