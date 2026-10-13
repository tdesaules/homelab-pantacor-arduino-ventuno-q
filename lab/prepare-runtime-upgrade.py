#!/usr/bin/env python3
"""Stage a BSP maintenance upgrade on Ubuntu, preserving the durable store."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from autonomous_boot import grub_default, grub_entry
from revision_names import valid_revision

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-recovery')
parser.add_argument('--revision')
parser.add_argument('--archive-k0s', action='store_true', help='Preserve the existing POC directory under a new name before initializing a fresh cluster')
args = parser.parse_args()
if args.revision is not None and not valid_revision(args.revision, allow_factory=False):
    parser.error('Invalid local revision (expected locals/<name>, up to 64 safe characters)')
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
assert inputs['autonomous_boot'] and (inputs.get('core_only') or inputs.get('k0s'))
env = os.environ | {'SSH_ASKPASS': str(ROOT / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
opts = ['-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=10']
host = 'arduino@192.168.1.20'
def ssh(command):
    return subprocess.check_output(['ssh', *opts, host, command], env=env, text=True).strip()

assert ssh('findmnt -n -o SOURCE /') == '/dev/mmcblk0p71'
assert ssh('uname -r') == inputs['kernel_release']
root_uuid = str(uuid.UUID(ssh('findmnt -n -o UUID /')))
# The marker is root-only; the known installation is revalidated by the installer.
install_id = '6491b61ba229489cb8bacb1719de7c2c'
upgrade_id = uuid.uuid4().hex
directory = ROOT / 'artifacts/runtime-upgrades' / upgrade_id
directory.mkdir(parents=True, mode=0o700)
(directory / 'grub-default.cfg').write_text(grub_default(root_uuid))
(directory / 'grub-entry.cfg').write_text(grub_entry(root_uuid, install_id))
sources = {'initramfs': args.output_dir / 'initramfs-ventuno-q.cpio.gz',
           'build-inputs.json': args.output_dir / 'build-inputs.json',
           'grub-default.cfg': directory / 'grub-default.cfg', 'grub-entry.cfg': directory / 'grub-entry.cfg'}
if inputs.get('k0s'):
    sources['k0s-root.squashfs'] = ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q/ventuno-k0s-image-ventuno-q.squashfs'
    sources['k0s_revision.py'] = ROOT / 'lab/k0s_revision.py'
    sources['resource_policy.py'] = ROOT / 'lab/resource_policy.py'
    sources['core-root.squashfs'] = ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q/ventuno-core-image-ventuno-q.squashfs'
hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items()}
request = {'install_id': install_id, 'upgrade_id': upgrade_id, 'root_uuid': root_uuid,
           'revision': args.revision or ('locals/k0s-050' if inputs.get('k0s') else 'locals/runtime-041'),
           'archive_k0s': args.archive_k0s, 'files': hashes}
(directory / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
stage = '/home/arduino/.cache/ventuno-runtime-upgrade-' + upgrade_id
ssh(f'test ! -e {stage} && mkdir -m 700 {stage}')
for name, source in sources.items():
    subprocess.run(['scp', '-q', *opts, str(source), host + ':' + stage + '/' + name], env=env, check=True)
subprocess.run(['scp', '-q', *opts, str(directory / 'request.json'), host + ':' + stage + '/request.json'], env=env, check=True)
print('UPGRADE_ID=' + upgrade_id)
