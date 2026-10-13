#!/usr/bin/env bash
# Board-specific offline migration from the qualified lab to the native contract.
# Run under Ubuntu after stopping Pantavisor. Never formats a partition.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

identity, archive_sha = sys.argv[1:]
assert re.fullmatch('[0-9a-f]{32}', identity)
assert re.fullmatch('[0-9a-f]{64}', archive_sha)
def run(*args): return subprocess.check_output(args, text=True).strip()
def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
assert run('findmnt', '-n', '-o', 'SOURCE', '/') == '/dev/mmcblk0p71'
assert run('findmnt', '-n', '-o', 'SOURCE', '/boot/efi') == '/dev/mmcblk0p69'
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert not run('losetup', '-j', '/boot/pantavisor/pvstore.ext4')
assert not run('lsblk', '-n', '-o', 'MOUNTPOINTS', '/dev/nvme0n1p1')
assert Path('/boot/pantavisor/install-id').read_text().strip() == '6491b61ba229489cb8bacb1719de7c2c'
assert 'pv_rev=locals/k0s-os-070' in run('grub-editenv', '/boot/pantavisor/state/grubenv', 'list')
assert 'ventuno_recovery=1' in run('grub-editenv', '/boot/pantavisor/state/boot-budget', 'list')
assert all(not line.split('=', 1)[1] for line in run('grub-editenv', '/boot/grub/grubenv', 'list').splitlines())
assert 'BootNext:' not in run('efibootmgr')
assert 'BootOrder: 0000' in run('efibootmgr')
assert shutil.disk_usage('/').free > 8 * 1024**3
archive = Path('/home/arduino/.cache') / ('ventuno-native-platform-' + identity + '.tar.gz')
assert sha(archive) == archive_sha
record = Path('/var/lib/ventuno-native-migrations') / identity
record.mkdir(parents=True, mode=0o700, exist_ok=False)
stage = record / 'package'
stage.mkdir(mode=0o700)
with tarfile.open(archive) as source:
    assert all(member.isdir() or member.isfile() for member in source.getmembers())
    source.extractall(stage, filter='data')
manifest = json.loads((stage / 'installation.json').read_text())
assert manifest['installId'] == identity and not manifest['emulated']
assert manifest['bootContract'] == 'emmc-file-store-v1' and manifest['revision'] == 'locals/0.1.0'
assert manifest['systemUUID'] == run('findmnt', '-n', '-o', 'UUID', '/')
assert manifest['espUUID'] == run('findmnt', '-n', '-o', 'UUID', '/boot/efi')
for name, checksum in manifest['files'].items():
    assert not name.startswith('/') and '..' not in Path(name).parts
    assert not (stage / name).is_symlink() and sha(stage / name) == checksum, name
actual = {str(path.relative_to(stage)) for path in stage.rglob('*') if path.is_file()}
assert actual == set(manifest['files']) | {'installation.json'}
assert not any(path.is_symlink() for path in stage.rglob('*'))
incoming = stage / 'system/boot/pantavisor'
assert (incoming / 'install-id').read_text().strip() == identity
subprocess.run(['e2fsck', '-f', '-n', str(incoming / 'pvstore.ext4')], check=True)
subprocess.run(['e2fsck', '-f', '-n', '/boot/pantavisor/pvstore.ext4'], check=True)
bootstrap = Path('/boot/efi/EFI/ubuntu/grub.cfg')
old = bootstrap.read_bytes()
assert len(old) < 256 and b'e5defb48-4df4-40fc-8f97-7d635b46fcb8' in old
shutil.copy2(bootstrap, record / 'esp-grub.cfg.before')
shutil.copy2('/boot/grub/grubenv', record / 'grubenv.before')
efi_name = 'ventuno-native-' + identity
destination = Path('/boot/efi/EFI') / efi_name
assert not destination.exists()
assert shutil.disk_usage('/boot/efi').free > 120 * 1024**2
shutil.copytree(stage / 'esp/EFI/ventuno', destination)
for name in ('bootaa64.efi', 'recoveryaa64.efi'):
    assert sha(destination / name) == manifest['files']['esp/EFI/ventuno/' + name]
dispatcher = (stage / 'esp-dispatcher.cfg').read_bytes()
assert ('/EFI/' + efi_name + '/bootaa64.efi').encode() in dispatcher
assert b'/boot/grub' not in dispatcher and b'configfile' not in dispatcher
subprocess.run(['grub-script-check', str(stage / 'esp-dispatcher.cfg')], check=True)
rollback = f'''#!/bin/sh
set -eu
test -f /run/ventuno-recovery
mkdir -p /mnt/rollback-system /mnt/rollback-esp
mount -t ext4 /dev/mmcblk0p71 /mnt/rollback-system
mount -t vfat /dev/mmcblk0p69 /mnt/rollback-esp
root=/mnt/rollback-system
record=$root/var/lib/ventuno-native-migrations/{identity}
test "$(cat "$root/boot/pantavisor/install-id")" = {identity}
test "$(cat "$record/previous-pantavisor/install-id")" = 6491b61ba229489cb8bacb1719de7c2c
test ! -e "$root/boot/pantavisor-failed-{identity}"
mv "$root/boot/pantavisor" "$root/boot/pantavisor-failed-{identity}"
mv "$record/previous-pantavisor" "$root/boot/pantavisor"
cp "$record/grubenv.before" "$root/boot/grub/grubenv"
cp "$record/esp-grub.cfg.before" /mnt/rollback-esp/EFI/ubuntu/grub.cfg.rollback
sync
mv /mnt/rollback-esp/EFI/ubuntu/grub.cfg.rollback /mnt/rollback-esp/EFI/ubuntu/grub.cfg
sync
umount /mnt/rollback-esp
umount /mnt/rollback-system
echo 'Previous installation restored; reboot -f returns to Ubuntu recovery.'
'''
(record / 'rollback.sh').write_text(rollback)
(record / 'rollback.sh').chmod(0o700)
receipt = {'installId': identity, 'previousInstallId': '6491b61ba229489cb8bacb1719de7c2c',
           'revision': manifest['revision'], 'archiveSha256': archive_sha,
           'previousEspSha256': hashlib.sha256(old).hexdigest(), 'espSha256': hashlib.sha256(dispatcher).hexdigest(),
           'previousStoreInode': Path('/boot/pantavisor/pvstore.ext4').stat().st_ino,
           'efiDirectory': str(destination), 'phase': 'prepared'}
def save(): (record / 'migration.json').write_text(json.dumps(receipt, indent=2) + '\n')
save()
subprocess.run(['sync'], check=True)
Path('/boot/pantavisor').rename(record / 'previous-pantavisor')
incoming.rename('/boot/pantavisor')
receipt['phase'] = 'system-staged'; save()
subprocess.run(['sync'], check=True)
temporary = bootstrap.with_name('grub.cfg.native')
with temporary.open('xb') as stream:
    stream.write(dispatcher); stream.flush(); os.fsync(stream.fileno())
temporary.replace(bootstrap)
subprocess.run(['sync'], check=True)
receipt['phase'] = 'native-selected'; save()
print(json.dumps(receipt, indent=2))
print('Native boot selected. Reboot is a separate operation. Rollback script:', record / 'rollback.sh')
PY
