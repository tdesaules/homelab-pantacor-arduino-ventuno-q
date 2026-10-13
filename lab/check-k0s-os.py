#!/usr/bin/env python3
"""Validate the k0s-ready OS policy and deploy its small Python API POC."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid
from local_updates import Session
from management_tools_session import exercise_management_tools
from persistent_session import wait_boot
from resource_policy import validate_node_budget

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--return-ubuntu', action='store_true')
parser.add_argument('--skip-client-checks', action='store_true', help='Reuse already completed interactive-client checks')
args = parser.parse_args()
directory = ROOT / 'artifacts/k0s-os' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, directory)
wait_boot(session, '6491b61ba229489cb8bacb1719de7c2c', timeout=240)
until = time.monotonic() + 240
while time.monotonic() < until:
    try:
        node = json.loads(session.run('kubectl get node ventuno-k0s -o json --request-timeout=15s'))
        progress = json.loads(session.control('steps', 'show-progress', 'current'))
        revision = session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')
        if revision == 'locals/k0s-os-070' and progress['status'] == 'DONE' and any(
            item['type'] == 'Ready' and item['status'] == 'True' for item in node['status']['conditions']): break
    except (RuntimeError, subprocess.TimeoutExpired): pass
    time.sleep(3)
else: raise RuntimeError('OS/cluster did not become ready')
until = time.monotonic() + 240
while time.monotonic() < until:
    try:
        # An existing cluster can become Ready before the worker-profile
        # reconciler acquires its lease and updates/restarts kubelet.
        node = json.loads(session.run('kubectl get node ventuno-k0s -o json'))
        config = json.loads(session.run('kubectl get --raw /api/v1/nodes/ventuno-k0s/proxy/configz'))
        resources = dict(line.split('=', 1) for line in session.run('cat /k0s-access/resources.status').splitlines())
        budget = validate_node_budget(node, config, resources)
        break
    except (RuntimeError, KeyError, AssertionError, subprocess.TimeoutExpired): time.sleep(3)
else: raise RuntimeError('Kubelet did not adopt the resource policy')
assert budget['allocatable_bytes'] > 12 * 1024 ** 3
assert budget['allocatable_cpu'] == '7500m'
assert session.run('cat /sys/fs/cgroup/cpu.weight').strip() == '200'
assert session.run('cat /sys/fs/cgroup/memory.max').strip() == '536870912'
(directory / 'resources.json').write_text(json.dumps(budget, indent=2) + '\n')
(directory / 'kubelet-config.json').write_text(json.dumps(config, indent=2) + '\n')
inputs = json.loads((ROOT / 'artifacts/prototype-k0s-os/build-inputs.json').read_text())
if not args.skip_client_checks:
    session.shells(inputs)
    exercise_management_tools(session)
# Preserve the cluster identity; only replace the known earlier POC workload.
existing = json.loads(session.run('kubectl -n ventuno-poc get deployment web -o json'))
images = [container['image'] for container in existing['spec']['template']['spec']['containers']]
assert all(image.startswith(('docker.io/library/busybox:', 'docker.io/library/python:')) for image in images), images
(directory / 'previous-workload.json').write_text(json.dumps(existing, indent=2) + '\n')
rendered = subprocess.check_output(['kubectl', 'kustomize', str(ROOT / 'examples/hello-api')])
session.run('kubectl apply -f -', data=rendered, timeout=90)
session.run('kubectl -n ventuno-poc rollout status deployment/web --timeout=240s', timeout=270)
until = time.monotonic() + 45
while time.monotonic() < until:
    try:
        with urllib.request.urlopen('http://192.168.1.20:30080/hello', timeout=10) as response:
            payload = json.load(response)
        with urllib.request.urlopen('http://192.168.1.20:30080/healthz', timeout=10) as response:
            health = json.load(response)
        if payload == {'message': 'Hello world', 'service': 'hello-api'} and health == {'status': 'ok'}: break
    except (OSError, ValueError) as error:
        if hasattr(error, 'close'): error.close()
    time.sleep(2)
else: raise RuntimeError('Hello API did not become reachable')
(directory / 'pods.json').write_text(session.run('kubectl get pods -A -o json'))
(directory / 'runtime.log').write_text(session.snapshot('runtime'))
(directory / 'result.json').write_text(json.dumps({'revision': revision, 'resource_policy': budget,
    'native_administration': True, 'hello_api': payload}, indent=2) + '\n')
print('PASS: resource policy, native administration and Python API. Logs:', directory)
print(json.dumps(budget, indent=2))
if args.return_ubuntu: session.reboot('ubuntu')
