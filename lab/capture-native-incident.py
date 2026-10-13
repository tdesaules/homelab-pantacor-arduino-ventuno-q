#!/usr/bin/env python3
"""Capture an incident from rescue with support/store already mounted read-only."""
import datetime
import argparse
import json
from pathlib import Path
import subprocess
import shlex
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--store-image', action='store_true', help='Also preserve the raw store, including its journal')
args = parser.parse_args()
output = ROOT / 'artifacts/native-incidents' / uuid.uuid4().hex
output.mkdir(parents=True, mode=0o700)
ssh = ['ssh', '-F', str(ROOT / 'artifacts/diagnostic-ssh/config'), 'ventuno-diagnostic']
subprocess.run(ssh + ['test -f /run/ventuno-recovery && grep " /mnt/boot-inspect ext4 ro," /proc/mounts && grep " /mnt/store-inspect ext4 ro," /proc/mounts'], check=True)
for name, command in {
    'boot.txt': 'cat /proc/cmdline /proc/uptime /proc/mounts; cat /mnt/boot-inspect/boot/pantavisor/state/boot-budget /mnt/boot-inspect/boot/pantavisor/state/grubenv',
    'dmesg.txt': 'dmesg',
    'core.txt': 'cat /mnt/store-inspect/disks/perm/core/data/boots /mnt/store-inspect/disks/perm/core/data/time.log /mnt/store-inspect/disks/perm/core/data/dhcp.state',
    'filesystems.txt': 'dumpe2fs -h /dev/mmcblk0p71; dumpe2fs -h /dev/loop250',
}.items():
    result = subprocess.run(ssh + [command], capture_output=True, timeout=60)
    (output / name).write_bytes(result.stdout + result.stderr)
walk = '''walk() { for p in "$1"/*; do
    if [ -L "$p" ]; then continue;
    elif [ -d "$p" ]; then (walk "$p");
    elif [ -f "$p" ]; then printf '%s\\0' "$p"; fi;
done; }; walk '''
for name, remote in {
    'bootstrap': '/mnt/boot-inspect/boot/pantavisor/logs',
    'runtime': '/mnt/store-inspect/logs',
    'pstore': '/sys/fs/pstore',
}.items():
    files = subprocess.check_output(ssh + [walk + shlex.quote(remote)], timeout=30).split(b'\0')
    for raw in files:
        if not raw: continue
        path = Path(raw.decode())
        target = output / name / path.relative_to(remote)
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with target.open('wb') as stream:
            subprocess.run(ssh + ['cat ' + shlex.quote(str(path))], stdout=stream, check=True, timeout=60)
(output / 'captured.json').write_text(json.dumps({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2))
if args.store_image:
    with (output / 'pvstore-before.ext4').open('wb') as stream:
        subprocess.run(ssh + ['dd if=/dev/loop250 bs=1048576'], stdout=stream, check=True, timeout=240)
print(output)
