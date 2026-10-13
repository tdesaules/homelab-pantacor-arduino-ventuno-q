#!/usr/bin/env python3
"""Stage a unique bounded trial over SSH; does not install GRUB or reboot."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import uuid
from revision_names import valid_revision

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/prototype-1084-ethernet-only')
parser.add_argument('--return-seconds', type=int, default=180, help='Bounded trial duration, 180..1800 seconds with a v4 PID 1 image')
parser.add_argument('--resume-trial', help='Clone the clean update store of this completed trial instead of using a pristine seed')
parser.add_argument('--boot-revision', default='0', help='Bounded application revision to boot (requires --resume-trial unless 0)')
args = parser.parse_args()
if args.resume_trial and not re.fullmatch('[0-9a-f]{32}', args.resume_trial):
    raise SystemExit('Invalid resume trial ID')
if not valid_revision(args.boot_revision) or (args.boot_revision != '0' and not args.resume_trial):
    raise SystemExit('Invalid boot revision or missing resume store')
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
if not inputs.get('bounded_trial'):
    raise SystemExit('A bounded-trial image is required')
if inputs.get('trial_supervisor_version') not in ((3, 4) if inputs.get('pid1_runtime') else (2,)):
    raise SystemExit('A matching bounded-trial supervisor/guardian version is required')
maximum = min(inputs.get('trial_max_seconds', 180), 1800) if inputs.get('trial_supervisor_version') == 4 else 180
if not 180 <= args.return_seconds <= maximum:
    raise SystemExit(f'Duration must be 180..{maximum} seconds for this image')
inputs['trial_return_seconds'] = args.return_seconds
inputs['boot_revision'] = args.boot_revision
env = os.environ | {'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'),
                   'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
opts = ['-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
        '-o', 'ConnectTimeout=10', '-o', 'NumberOfPasswordPrompts=1']
host = 'arduino@192.168.1.20'

def ssh(command):
    return subprocess.check_output(['ssh', *opts, host, command], env=env, text=True).strip()

release = inputs['kernel_release']
if ssh('uname -r') != release or ssh('findmnt -n -o SOURCE /') != '/dev/mmcblk0p71':
    raise SystemExit('Unexpected kernel/root device on board')
root_uuid = str(uuid.UUID(ssh('findmnt -n -o UUID /')))
if inputs.get('network_profile'):
    if ssh('cat /sys/class/net/end0/address') != inputs['network_profile']['ethernet_mac']:
        raise SystemExit('Ethernet MAC changed: refresh the profile and reassemble before testing')
trial = uuid.uuid4().hex
directory = root / 'artifacts/trials' / trial
directory.mkdir(parents=True)
(directory / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
(directory / 'trial-id').write_text(trial + '\n')
subprocess.run(['python3', str(root / 'lab/generate-grub-entry.py'),
                '--rootfs-uuid', root_uuid, '--output-dir', str(directory), '--trial-id', trial], check=True)
sources = {f'vmlinuz-{release}': args.output_dir / f'vmlinuz-{release}',
           'initramfs-ventuno-q.cpio.gz': args.output_dir / 'initramfs-ventuno-q.cpio.gz',
           'grub-diagnostic.cfg': directory / 'grub-diagnostic.cfg',
           'trial-id': directory / 'trial-id', 'build-inputs.json': directory / 'build-inputs.json'}
if inputs.get('embedded_runtime'):
    assert inputs.get('runtime_storage'), 'Build the first revision before transfer'
    sources['pvstore.ext4.gz'] = args.output_dir / 'pvstore.ext4.gz'
hashes = {}
for name, path in sources.items():
    with path.open('rb') as stream:
        hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
request = {'trial_id': trial, 'kernel_release': release, 'rootfs_uuid': root_uuid, 'boot_revision': args.boot_revision,
           'entry_id': 'pantavisor-trial-' + trial, 'return_seconds': args.return_seconds, 'files': hashes}
(directory / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
stage = '/home/arduino/.cache/ventuno-trial-' + trial
ssh(f'test ! -e {stage} && mkdir -p -m 700 {stage}')
subprocess.run(['scp', '-q', *opts, *map(str, sources.values()), str(directory / 'request.json'),
                host + ':' + stage + '/'], env=env, check=True)
if args.resume_trial:
    subprocess.run(['python3', str(root / 'lab/run-board-check.py'), '--sudo',
                    '--argument', args.resume_trial, '--argument', trial,
                    str(root / 'lab/prepare-resume-store.sh')], check=True)
    for name in ('request.json', 'build-inputs.json', 'resume-store.json'):
        subprocess.run(['scp', '-q', *opts, host + ':' + stage + '/' + name, str(directory / name)], env=env, check=True)
print('TRIAL_ID=' + trial)
print('Local record:', directory)
print('Remote staging:', stage)
