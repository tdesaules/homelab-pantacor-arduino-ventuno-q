#!/usr/bin/env bash
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
default_boot = len(sys.argv) == 3 and sys.argv[2] == '--default'
assert len(sys.argv) == 2 or default_boot
assert re.fullmatch('[0-9a-f]{32}', install_id)
record = json.loads((Path('/var/lib/ventuno-autonomous') / install_id / 'installation.json').read_text())
assert Path('/boot/pantavisor/install-id').read_text().strip() == install_id
assert hashlib.sha256(Path('/boot/grub/grub.cfg').read_bytes()).hexdigest() == record['installed_grub_sha256']
assert hashlib.sha256(Path('/etc/default/grub').read_bytes()).hexdigest() == record['defaults_sha256']
assert re.search(r'^GRUB_DEFAULT=0$', Path('/etc/default/grub').read_text(), re.M)
assert all(not line.split('=', 1)[1] for line in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines())
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert not subprocess.check_output(['losetup', '-j', '/boot/pantavisor/pvstore.ext4'], text=True).strip()
store = Path('/boot/pantavisor/pvstore.ext4')
assert store.stat().st_ino == record['store_inode'] and store.stat().st_size == record['store_size']
assert subprocess.check_output(['blkid', '-p', '-s', 'UUID', '-o', 'value', str(store)], text=True).strip() == record['store_uuid']
header = subprocess.check_output(['dumpe2fs', '-h', str(store)], stderr=subprocess.DEVNULL, text=True)
assert 'needs_recovery' not in header and 'orphan_present' not in header
subprocess.run(['e2fsck', '-f', '-n', '/boot/pantavisor/pvstore.ext4'], check=True)
for name in ('kernel', 'initramfs'):
    assert hashlib.sha256((Path('/boot/pantavisor') / name).read_bytes()).hexdigest() == record['files'][name]
subprocess.run(['grub-editenv', '/boot/pantavisor/state/boot-budget', 'set', 'ventuno_boots=0', 'ventuno_recovery=0'], check=True)
if default_boot:
    assert hashlib.sha256(Path('/etc/grub.d/09_ventuno_default').read_bytes()).hexdigest() == record['default_snippet_sha256']
else:
    subprocess.run(['grub-reboot', 'pantavisor-persistent'], check=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-autonomous-start', '/usr/bin/systemctl', 'reboot'], check=True)
print('Default boot scheduled without next_entry.' if default_boot else 'One-shot activation scheduled.')
PY
