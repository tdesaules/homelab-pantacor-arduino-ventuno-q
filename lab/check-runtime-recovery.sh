#!/usr/bin/env bash
# Read-only recovery checks, without historical diagnostic counter assumptions.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

install_id = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', install_id)
root = Path('/boot/pantavisor')
assert (root / 'install-id').read_text().strip() == install_id
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
record = json.loads((Path('/var/lib/ventuno-autonomous') / install_id / 'installation.json').read_text())
def env(path):
    return dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', str(path), 'list'], text=True).splitlines())
assert not env('/boot/grub/grubenv').get('next_entry')
assert env(root / 'state/boot-budget')['ventuno_recovery'] == '1'
assert hashlib.sha256(Path('/etc/grub.d/09_ventuno_default').read_bytes()).hexdigest() == record['default_snippet_sha256']
store = root / 'pvstore.ext4'
assert store.stat().st_ino == record['store_inode'] and store.stat().st_size == record['store_size']
assert not subprocess.check_output(['losetup', '-j', str(store)], text=True).strip()
device = Path('/dev/disk/by-uuid/5ccb2c2f-c0f7-44a1-a291-b261a7d060a3').resolve()
assert device == Path('/dev/nvme0n1p1')
assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(device)], text=True).strip()
for path in (store, device):
    header = subprocess.check_output(['dumpe2fs', '-h', str(path)], stderr=subprocess.DEVNULL, text=True)
    assert 'needs_recovery' not in header and 'orphan_present' not in header
    subprocess.run(['e2fsck', '-f', '-n', str(path)], check=True)
identity = subprocess.check_output(['debugfs', '-R', 'cat /perm/diagnostic/data/identity', str(device)], stderr=subprocess.DEVNULL, text=True).strip()
assert identity == '7877e500-a853-430e-b506-a423eebb1ca1'
poc_identity = subprocess.check_output(['debugfs', '-R', 'cat /perm/k0s/workloads/poc/identity', str(device)], stderr=subprocess.DEVNULL, text=True).strip()
if env(root / 'state/grubenv').get('pv_rev') == 'locals/k0s-os-070':
    assert poc_identity == 'a565c9ca-1cbb-4a8c-b946-9069bdaefa84'
parts = subprocess.check_output(['lsblk', '-nr', '-o', 'TYPE', '/dev/mmcblk0'], text=True).splitlines()
assert parts.count('part') == 71
print(json.dumps({'ubuntu_recovery': True, 'recovery_latched': True, 'store_inode': store.stat().st_ino,
                  'filesystems_clean': True, 'retained_identity': identity, 'emmc_partitions': 71,
                  'retained_poc_identity': poc_identity or None,
                  'revision_env': env(root / 'state/grubenv')}, indent=2))
PY
