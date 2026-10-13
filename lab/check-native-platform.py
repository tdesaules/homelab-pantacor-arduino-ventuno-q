#!/usr/bin/env python3
"""Qualify a native k0s boot and optionally a normal reboot, preserving the cluster."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid
from local_updates import Session
from persistent_session import wait_boot
from resource_policy import validate_node_budget

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--installation', type=Path, required=True)
parser.add_argument('--previous-audit', type=Path, required=True)
parser.add_argument('--reboot', action='store_true')
parser.add_argument('--timeout', type=int, default=240)
args = parser.parse_args()
manifest = json.loads((args.installation / 'installation.json').read_text())
previous = json.loads((args.previous_audit / 'nodes.json').read_text())['items'][0]
output = ROOT / 'artifacts/native-platform' / uuid.uuid4().hex
output.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, output)
boot = None
observations = []
for cycle in range(2 if args.reboot else 1):
    boot = wait_boot(session, manifest['installId'], previous=boot, timeout=300)
    until = time.monotonic() + args.timeout
    while time.monotonic() < until:
        try:
            revision = session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')
            # A directly provisioned boot seed has no updater progress record.
            # Do not confuse update history with observed runtime readiness.
            steps = json.loads(session.control('steps', 'ls'))
            initial_seed = any(step['name'] == manifest['revision'] and step.get('progress') == {} for step in steps)
            progress = {} if initial_seed else json.loads(session.control('steps', 'show-progress', 'current'))
            revision_status = 'DONE' if progress.get('status') == 'DONE' else 'INITIAL_SEED' if initial_seed else 'UNREADY'
            node = json.loads(session.run('kubectl get node ventuno-k0s -o json --request-timeout=10s'))
            guard = dict(line.split('=', 1) for line in session.run('cat /trial-status/guard.status').splitlines())
            config = json.loads(session.run('kubectl get --raw /api/v1/nodes/ventuno-k0s/proxy/configz --request-timeout=10s'))
            resources = dict(line.split('=', 1) for line in session.run('cat /k0s-access/resources.status').splitlines())
            budget = validate_node_budget(node, config, resources)
            health = dict(line.split('=', 1) for line in session.run('cat /trial-status/health.status').splitlines())
            if (revision == manifest['revision'] and revision_status != 'UNREADY' and int(guard['elapsed']) >= 130
                    and health.get('ready') == '1'
                    and any(x['type'] == 'Ready' and x['status'] == 'True' for x in node['status']['conditions'])):
                break
        except (RuntimeError, ValueError, KeyError, AssertionError, subprocess.TimeoutExpired) as error:
            (output / 'last-readiness-error.txt').write_text(repr(error))
        time.sleep(5)
    else:
        detail = (output / 'last-readiness-error.txt').read_text() if (output / 'last-readiness-error.txt').exists() else 'readiness predicate not satisfied'
        raise SystemExit('Native qualification failed: ' + detail + '; evidence: ' + str(output))
    assert node['metadata']['uid'] == previous['metadata']['uid'], 'Cluster node identity changed'
    assert guard['host_pid1_name'] == 'pantavisor' and guard['watchdog'] == 'armed'
    with urllib.request.urlopen('http://192.168.1.20:30080/hello', timeout=15) as response:
        api = json.load(response)
    assert api == {'message': 'Hello world', 'service': 'hello-api'}
    starts = int(session.run('cat /data/boots').strip())
    if observations: assert starts == observations[-1]['coreStarts'] + 1
    observation = {'bootId': boot, 'revision': revision, 'revisionStatus': revision_status, 'progress': progress, 'guard': guard,
                   'nodeUID': node['metadata']['uid'], 'budget': budget, 'coreStarts': starts, 'api': api}
    observations.append(observation)
    (output / f'cycle-{cycle}.json').write_text(json.dumps(observation, indent=2))
    (output / f'pods-{cycle}.json').write_text(session.run('kubectl get pods -A -o json'))
    (output / f'core-release-{cycle}.json').write_text(session.run('cat /etc/ventuno-core-release'))
    (output / f'app-storage-{cycle}.txt').write_text(session.run('cat /trial-status/app-storage.status'))
    if args.reboot and cycle == 0: session.reboot()
print('PASS: native revision, stable core, preserved k0s identity, resource policy and API:', output)
