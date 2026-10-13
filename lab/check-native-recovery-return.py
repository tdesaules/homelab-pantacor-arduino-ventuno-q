#!/usr/bin/env python3
"""Check that the original qualified runtime was restored after rescue trials."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid
from local_updates import Session
from persistent_session import wait_boot

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / 'artifacts/native-hardware-return' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, directory)
wait_boot(session, '6491b61ba229489cb8bacb1719de7c2c', timeout=240)
until = time.monotonic() + 240
while time.monotonic() < until:
    try:
        revision = session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')
        progress = json.loads(session.control('steps', 'show-progress', 'current'))
        node = json.loads(session.run('kubectl get node ventuno-k0s -o json --request-timeout=10s'))
        guard = session.run('cat /trial-status/guard.status')
        fields = dict(line.split('=', 1) for line in guard.splitlines())
        if (revision == 'locals/k0s-os-070' and progress['status'] == 'DONE' and int(fields['elapsed']) >= 130
                and any(x['type'] == 'Ready' and x['status'] == 'True' for x in node['status']['conditions'])):
            break
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        pass
    time.sleep(5)
else:
    raise SystemExit('Original runtime did not become ready; evidence: ' + str(directory))
with urllib.request.urlopen('http://192.168.1.20:30080/hello', timeout=10) as response:
    payload = json.load(response)
assert payload == {'message': 'Hello world', 'service': 'hello-api'}
(directory / 'node.json').write_text(json.dumps(node, indent=2))
(directory / 'progress.json').write_text(json.dumps(progress, indent=2))
(directory / 'guard.txt').write_text(guard)
(directory / 'pods.json').write_text(session.run('kubectl get pods -A -o json'))
(directory / 'result.json').write_text(json.dumps({'revision': revision, 'status': 'DONE', 'nodeReady': True, 'api': payload}, indent=2))
print('PASS: original runtime, Kubernetes and API restored:', directory)
