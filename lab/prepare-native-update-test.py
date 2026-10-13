#!/usr/bin/env python3
"""Prepare a real core-image update and a deliberately unready revision; no activation."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
from local_updates import Session

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--core-image', type=Path, required=True)
parser.add_argument('--core-release', type=Path, required=True)
args = parser.parse_args()
output = ROOT / 'artifacts/native-update-tests' / uuid.uuid4().hex
(output / 'objects').mkdir(parents=True, mode=0o700)
output.chmod(0o700)
session = Session('192.168.1.20', 2222, output)
base = json.loads(session.control('steps', 'get', 'current'))
assert base == json.loads((args.state / 'state.json').read_text()), 'Current revision differs from the source state'
assert session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"') == 'locals/0.1.0'
release = json.loads(args.core_release.read_text())
assert release['version'] == '0.8.1'
with args.core_image.open('rb') as stream: core_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
shutil.copyfile(args.core_image, output / 'objects' / core_sha)

def put(data):
    checksum = hashlib.sha256(data).hexdigest()
    (output / 'objects' / checksum).write_bytes(data)
    return checksum

upgrade = copy.deepcopy(base)
upgrade['core/root.squashfs'] = core_sha
config = (args.state / 'objects' / base['core/lxc.container.conf']).read_bytes()
assert hashlib.sha256(config).hexdigest() == base['core/lxc.container.conf']
if b' boot-state ' not in config:
    config += b'lxc.mount.entry = /mnt/pv-system/boot/pantavisor/state boot-state none bind,ro,create=dir 0 0\n'
upgrade['core/lxc.container.conf'] = put(config)
upgrade['_config/core/etc/ventuno-os-release'] = put(b'VERSION=0.2.0\n')
fault = copy.deepcopy(upgrade)
broken, count = re.subn(rb'(?m)^lxc.init.cmd = .+$',
                       b'lxc.init.cmd = /usr/sbin/init.lxc.static --name core -- /bin/sleep 3600', config)
assert count == 1
fault['core/lxc.container.conf'] = put(broken)
for name, state in (('base', base), ('upgrade', upgrade), ('fault', fault)):
    assert state['bsp/kernel.img'] == base['bsp/kernel.img'] and state['bsp/pantavisor'] == base['bsp/pantavisor']
    (output / (name + '.json')).write_text(json.dumps(state, sort_keys=True, separators=(',', ':')) + '\n')
(output / 'manifest.json').write_text(json.dumps({'base': 'locals/0.1.0', 'upgrade': 'locals/0.2.0',
    'fault': 'locals/0.2.0-unready', 'coreRelease': release,
    'bspChanged': False, 'purpose': 'core image upgrade, explicit downgrade and failed try-boot rollback'}, indent=2))
print(output)
