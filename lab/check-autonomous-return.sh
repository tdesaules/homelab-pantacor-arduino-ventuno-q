#!/usr/bin/env bash
# Verify recovery and durable state under Ubuntu; leave the persistent entry installed.
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
audit = Path('/var/lib/ventuno-autonomous') / install_id
record = json.loads((audit / 'installation.json').read_text())
inputs = json.loads((root / 'build-inputs.json').read_text())
assert (root / 'install-id').read_text().strip() == install_id
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
assert hashlib.sha256(Path('/boot/grub/grub.cfg').read_bytes()).hexdigest() == record['installed_grub_sha256']
assert hashlib.sha256(Path('/etc/default/grub').read_bytes()).hexdigest() == record['defaults_sha256']
env = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
assert not dict(line.split('=', 1) for line in env.splitlines()).get('next_entry')
store = root / 'pvstore.ext4'
assert store.stat().st_ino == record['store_inode'] and store.stat().st_size == record['store_size']
assert subprocess.check_output(['blkid', '-p', '-s', 'UUID', '-o', 'value', str(store)], text=True).strip() == record['store_uuid']
assert not subprocess.check_output(['losetup', '-j', str(store)], text=True).strip()
nvme = Path('/dev/disk/by-uuid') / inputs['app_storage']['filesystem_uuid']
assert nvme.resolve() == Path('/dev/nvme0n1p1')
assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(nvme)], text=True).strip()
for image in (store, nvme):
    header = subprocess.check_output(['dumpe2fs', '-h', str(image)], stderr=subprocess.DEVNULL, text=True)
    assert 'needs_recovery' not in header and 'orphan_present' not in header
    subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)

def read(image, path):
    return subprocess.check_output(['debugfs', '-R', 'cat ' + path, str(image)], stderr=subprocess.DEVNULL, text=True).strip()

logs = {}
for path in sorted((root / 'logs').glob('*.log')):
    text = path.read_text(errors='replace')
    def field(key):
        found = re.search('^' + re.escape(key) + '=(.*)$', text, re.M)
        return found.group(1) if found else None
    logs[path.name] = {key: field(key) for key in ('TRIAL_BOOT_ID', 'HOST_PID1_NAME', 'AUTONOMOUS_NEXT', 'APPDATA_CLEANLY_UNMOUNTED', 'RUNTIME_CLEANUP_UNMOUNT_FAILURES')}
    assert field('APPDATA_CLEANLY_UNMOUNTED') == '1' and field('RUNTIME_CLEANUP_UNMOUNT_FAILURES') == '0'
assert sum(item['AUTONOMOUS_NEXT'] == 'pantavisor' for item in logs.values()) >= 3
assert any(item['AUTONOMOUS_NEXT'] == 'ubuntu' for item in logs.values())
progress = {rev: json.loads(read(store, '/trails/' + rev + '/.pv/progress')) for rev in ('locals/app-v2', 'locals/app-unready')}
assert progress['locals/app-v2']['status'] == 'DONE' and progress['locals/app-unready']['status'] == 'ERROR'
bootenv = subprocess.check_output(['grub-editenv', str(root / 'state/grubenv'), 'list'], text=True)
assert 'pv_rev=locals/app-v2' in bootenv.splitlines()
result = {'install_id': install_id, 'ubuntu_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'ubuntu_default_preserved': True, 'next_entry_cleared': True, 'store_inode': store.stat().st_ino,
          'store_uuid': record['store_uuid'], 'store_size': store.stat().st_size,
          'boot_env': bootenv, 'boot_logs': logs, 'progress': progress,
          'core_starts': int(read(store, '/disks/perm/core/data/boots')),
          'application': json.loads(read(nvme, '/perm/diagnostic/data/heartbeat.json'))}
(audit / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
systemctl --failed --no-pager
systemctl is-active ssh NetworkManager arduino-app-cli arduino-router
