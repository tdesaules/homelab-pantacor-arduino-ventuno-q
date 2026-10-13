#!/usr/bin/env python3
"""Stage a new durable Pantavisor installation; does not install GRUB or reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from autonomous_boot import grub_entry

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-autonomous')
args = parser.parse_args()
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
assert inputs['autonomous_boot'] and not inputs['bounded_trial'] and inputs['trial_supervisor_version'] == 5
assert inputs['runtime_storage']['size'] == 1024 * 1024 * 1024
env = os.environ | {'SSH_ASKPASS': str(ROOT / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
opts = ['-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=10']
host = 'arduino@192.168.1.20'
def ssh(command): return subprocess.check_output(['ssh', *opts, host, command], env=env, text=True).strip()
assert ssh('uname -r') == inputs['kernel_release']
assert ssh('findmnt -n -o SOURCE /') == '/dev/mmcblk0p71'
assert ssh('cat /sys/class/net/end0/address') == inputs['network_profile']['ethernet_mac']
root_uuid = str(uuid.UUID(ssh('findmnt -n -o UUID /')))
install_id = uuid.uuid4().hex
directory = ROOT / 'artifacts/autonomous' / install_id
directory.mkdir(parents=True)
(directory / 'install-id').write_text(install_id + '\n')
(directory / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
(directory / 'grub-entry.cfg').write_text(grub_entry(root_uuid, install_id))
sources = {'kernel': args.output_dir / ('vmlinuz-' + inputs['kernel_release']),
           'initramfs': args.output_dir / 'initramfs-ventuno-q.cpio.gz',
           'pvstore.ext4.gz': args.output_dir / 'pvstore.ext4.gz', 'grubenv': args.output_dir / 'boot-state.grubenv',
           **{name: directory / name for name in ('install-id', 'build-inputs.json', 'grub-entry.cfg')}}
hashes = {}
for name, path in sources.items():
    with path.open('rb') as stream: hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
request = {'install_id': install_id, 'root_uuid': root_uuid, 'files': hashes}
(directory / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
stage = '/home/arduino/.cache/ventuno-autonomous-' + install_id
ssh(f'test ! -e {stage} && mkdir -p -m 700 {stage}')
for name, source in sources.items():
    subprocess.run(['scp', '-q', *opts, str(source), host + ':' + stage + '/' + name], env=env, check=True)
subprocess.run(['scp', '-q', *opts, str(directory / 'request.json'), host + ':' + stage + '/request.json'], env=env, check=True)
print('INSTALL_ID=' + install_id)
print('Local record:', directory)
