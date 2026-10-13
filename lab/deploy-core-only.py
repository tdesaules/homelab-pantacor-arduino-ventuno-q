#!/usr/bin/env python3
"""Install core-only, wait for its native reboot/commit, and leave SSH available."""
import argparse
import json
from pathlib import Path
import time
from diagnostic_ssh import ROOT
from local_updates import Session
from persistent_session import wait_boot
from core_only import core_only_ready

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--install-id', default='6491b61ba229489cb8bacb1719de7c2c')
args = parser.parse_args()
session = Session('192.168.1.20', 2222, args.bundle)
assert 'ventuno_install=' + args.install_id in session.run('cat /proc/cmdline')
before = session.run('cat /proc/sys/kernel/random/boot_id').strip()
state = json.loads((args.bundle / 'state.json').read_text())
release = json.loads((args.bundle / 'release.json').read_text())
current = json.loads(session.control('steps', 'get', 'current'))
base_path = args.bundle / 'base-state.json'
if base_path.exists():
    assert current == json.loads(base_path.read_text()), 'The active revision changed since preparation'
platforms = {value['name'] for key, value in current.items() if key.endswith('/run.json') and isinstance(value, dict) and value.get('type') == 'lxc'}
assert platforms <= {'core', 'diagnostic'}, 'Unrelated applications appeared; refusing replacement'
assert all(current[key] == value for key, value in state.items() if key.startswith('bsp/'))
for path in (args.bundle / 'objects').iterdir():
    remote = '/tmp/ventuno-core-only-' + path.name
    session.upload(path, remote)
    session.control('objects', 'put', remote, path.name)
session.upload(args.bundle / 'state.json', '/tmp/ventuno-core-only.json')
session.control('steps', 'put', '/tmp/ventuno-core-only.json', 'locals/core-only-040')
session.reboot_command('ventuno-revision-status control cmd run-commit locals/core-only-040')
after = wait_boot(session, args.install_id, before)
until = time.monotonic() + 100
while time.monotonic() < until:
    try:
        text = session.snapshot('core-only-active')
    except RuntimeError:
        time.sleep(2)
        continue
    if core_only_ready(text, 'locals/core-only-040', release): break
    time.sleep(2)
else: raise SystemExit('Core-only did not reach DONE/READY')
session.shells({'core_image': {'release': release}})
assert session.run('test ! -e /diagnostic-data && echo DETACHED').strip() == 'DETACHED'
result = {'revision': 'locals/core-only-040', 'status': 'DONE', 'containers': ['core'],
          'before_core_boot_id': before, 'core_boot_id': after, 'core_version': release['version']}
(args.bundle / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
print('PASS: diagnostic decommissioned, Bash-only core ready; SSH left running')
