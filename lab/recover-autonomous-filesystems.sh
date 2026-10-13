#!/usr/bin/env bash
# Preserve the store and all allocated NVMe blocks before ext4 journal replay.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path('/boot/pantavisor')
install_id = root.joinpath('install-id').read_text().strip()
assert install_id == '6491b61ba229489cb8bacb1719de7c2c'
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
record = json.loads((Path('/var/lib/ventuno-autonomous') / install_id / 'installation.json').read_text())
store = root / 'pvstore.ext4'
nvme = Path('/dev/nvme0n1p1')
assert not store.is_symlink() and store.stat().st_ino == record['store_inode'] and store.stat().st_size == record['store_size']
assert not subprocess.check_output(['losetup', '-j', str(store)], text=True).strip()
assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(nvme)], text=True).strip()
assert not list(Path('/sys/class/block/nvme0n1p1/holders').iterdir())
assert Path('/sys/class/nvme/nvme0/serial').read_text().strip() == '0012327000631'
assert subprocess.check_output(['blkid', '-p', '-s', 'UUID', '-o', 'value', str(nvme)], text=True).strip() == '5ccb2c2f-c0f7-44a1-a291-b261a7d060a3'
assert shutil.which('e2image') and shutil.disk_usage('/').free > 8 * 1024 ** 3
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/lib/ventuno-autonomous') / install_id / ('recovery-' + stamp)
backup.mkdir(mode=0o700)
print('Recovery backup:', backup, flush=True)
shutil.copy2(store, backup / 'pvstore.before.ext4')
(backup / 'pvstore.before.ext4').chmod(0o600)
shutil.copytree(root / 'state', backup / 'state.before')
subprocess.run(['e2image', '-Q', '-a', str(nvme), str(backup / 'nvme-allocated.before.qcow2')], check=True)
(backup / 'nvme-allocated.before.qcow2').chmod(0o600)
subprocess.run(['sync'], check=True)
result = {'backup': str(backup), 'filesystems': {}}
for path in (store, nvme):
    replay = subprocess.run(['e2fsck', '-p', str(path)], capture_output=True, text=True)
    (backup / (path.name + '.replay.log')).write_text(replay.stdout + replay.stderr)
    print(replay.stdout + replay.stderr, flush=True)
    assert replay.returncode in (0, 1), f'Replay failed for {path}: {replay.returncode}'
    header = subprocess.check_output(['dumpe2fs', '-h', str(path)], stderr=subprocess.DEVNULL, text=True)
    assert 'needs_recovery' not in header and 'orphan_present' not in header
    check = subprocess.run(['e2fsck', '-f', '-n', str(path)], capture_output=True, text=True)
    (backup / (path.name + '.check.log')).write_text(check.stdout + check.stderr)
    print(check.stdout + check.stderr, flush=True)
    check.check_returncode()
    result['filesystems'][str(path)] = {'replay_exit': replay.returncode, 'check_exit': check.returncode}
for name in ('boots', 'identity', 'heartbeat.json'):
    data = subprocess.check_output(['debugfs', '-R', 'cat /perm/diagnostic/data/' + name, str(nvme)], stderr=subprocess.DEVNULL, text=True)
    print(name + ': ' + data.strip())
    result[name] = data.strip()
assert result['identity'] == '7877e500-a853-430e-b506-a423eebb1ca1'
print('### Runtime log directory')
subprocess.run(['debugfs', '-R', 'ls -l /logs/locals/app-v2', str(store)], check=True)
(backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
