#!/usr/bin/env python3
"""Capture the running state and retire the diagnostic process before the core update."""
import hashlib
import json
from pathlib import Path
import time
import uuid
from diagnostic_ssh import ROOT
from local_updates import Session

directory = ROOT / 'artifacts/decommission' / uuid.uuid4().hex
directory.mkdir(parents=True)
session = Session('192.168.1.20', 2222, directory)
assert 'ventuno_install=6491b61ba229489cb8bacb1719de7c2c' in session.run('cat /proc/cmdline')
state = json.loads(session.control('steps', 'get', 'current'))
config = session.control('objects', 'get', state['core/lxc.container.conf']).encode()
assert hashlib.sha256(config).hexdigest() == state['core/lxc.container.conf']
(directory / 'base-state.json').write_text(json.dumps(state, indent=2) + '\n')
(directory / 'base-core.conf').write_bytes(config)
session.control('containers', 'stop', 'diagnostic')
for _ in range(15):
    containers = json.loads(session.control('containers', 'ls'))
    app = next(item for item in containers if item['name'] == 'diagnostic')
    if app['status'] == 'STOPPED' and app['user_stopped'] in (True, 'true'): break
    time.sleep(1)
else: raise SystemExit('Diagnostic did not stop')
for name in ('boots', 'identity', 'heartbeat.json'):
    (directory / ('retained-' + name)).write_text(session.run('cat /diagnostic-data/' + name))
print('Diagnostic stopped; core remains available. Captured state:', directory)
