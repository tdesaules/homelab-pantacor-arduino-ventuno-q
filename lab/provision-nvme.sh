#!/usr/bin/env bash
# One-time GPT/ext4 creation on the exact empty NVMe authorized for application data.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import uuid

profile = json.loads(sys.argv[1])
assert profile['schema'] == 1 and profile['name'] == 'nvme-apps'
assert profile['device'] == '/dev/nvme0n1'
assert profile['model'] == 'NE-128 2242' and profile['serial'] == '0012327000631'
assert profile['size_bytes'] == 128035676160 and profile['label'] == 'pv-appdata'
for key in ('filesystem_uuid', 'partition_uuid', 'disk_guid'):
    assert str(uuid.UUID(profile[key])) == profile[key]
device = profile['device']
partition = device + 'p1'
for tool in ('sfdisk', 'udevadm', 'mkfs.ext4', 'e2fsck', 'mount', 'umount', 'blkid', 'blockdev', 'lsblk', 'wipefs'):
    assert shutil.which(tool), f'Missing tool: {tool}'

def run(*args):
    return subprocess.check_output(args, text=True).strip()

assert run('findmnt', '-n', '-o', 'SOURCE', '/') == '/dev/mmcblk0p71'
assert Path('/sys/class/nvme/nvme0/model').read_text().strip() == profile['model']
assert Path('/sys/class/nvme/nvme0/serial').read_text().strip() == profile['serial']
assert int(run('blockdev', '--getsize64', device)) == profile['size_bytes']
assert not list(Path('/sys/class/block/nvme0n1/holders').iterdir())
assert not run('swapon', '--show', '--noheadings')
inventory = json.loads(run('lsblk', '-b', '-J', '-o', 'PATH,TYPE,MOUNTPOINTS', device))['blockdevices']
assert len(inventory) == 1 and not inventory[0].get('children'), 'Existing partitions: refusing to reformat'
assert not any(inventory[0]['mountpoints']), 'NVMe is mounted'
assert not json.loads(run('wipefs', '-n', '-J', device))['signatures'], 'Existing signatures: refusing to reformat'
audit = Path('/var/lib/ventuno-nvme') / profile['filesystem_uuid']
audit.mkdir(parents=True, mode=0o700, exist_ok=False)
(audit / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n')
# Retain the original GPT areas, not a full-disk backup.
with open(device, 'rb', buffering=0) as disk:
    first = disk.read(1024 * 1024)
    disk.seek(profile['size_bytes'] - 1024 * 1024)
    last = disk.read(1024 * 1024)
(audit / 'first-MiB.before').write_bytes(first)
(audit / 'last-MiB.before').write_bytes(last)
subprocess.run(['sync'], check=True)
layout = (f"label: gpt\nlabel-id: {profile['disk_guid']}\nunit: sectors\n\n"
          f"start=2048, type=linux, uuid={profile['partition_uuid']}, name=\"pv-appdata\"\n")
subprocess.run(['sfdisk', '--wipe', 'never', '--wipe-partitions', 'never', device], input=layout, text=True, check=True)
subprocess.run(['udevadm', 'settle', '--timeout=30'], check=True)
assert run('lsblk', '-n', '-o', 'PKNAME', partition) == 'nvme0n1'
assert run('blkid', '-s', 'PARTUUID', '-o', 'value', partition) == profile['partition_uuid']
subprocess.run(['mkfs.ext4', '-F', '-L', profile['label'], '-U', profile['filesystem_uuid'], '-m', '0',
                '-E', 'lazy_itable_init=0,lazy_journal_init=0', partition], check=True)
assert run('blkid', '-s', 'UUID', '-o', 'value', partition) == profile['filesystem_uuid']
assert run('blkid', '-p', '-s', 'PART_ENTRY_UUID', '-o', 'value', partition) == profile['partition_uuid']
with tempfile.TemporaryDirectory(prefix='ventuno-nvme-', dir='/mnt') as mountpoint:
    subprocess.run(['mount', '-t', 'ext4', '-o', 'nosuid,nodev', partition, mountpoint], check=True)
    try:
        root = Path(mountpoint)
        (root / '.ventuno-app-storage').write_text('ventuno-appdata-v1 ' + profile['filesystem_uuid'] + '\n')
        (root / 'perm/diagnostic/data').mkdir(parents=True, mode=0o755)
        (root / 'provisioning.json').write_text(json.dumps(profile, indent=2) + '\n')
        subprocess.run(['sync'], check=True)
    finally:
        subprocess.run(['umount', mountpoint], check=True)
subprocess.run(['e2fsck', '-f', '-n', partition], check=True)
result = {'status': 'provisioned', 'profile': profile, 'layout': json.loads(run('sfdisk', '--json', device)),
          'first_before_sha256': hashlib.sha256(first).hexdigest(), 'last_before_sha256': hashlib.sha256(last).hexdigest()}
(audit / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
