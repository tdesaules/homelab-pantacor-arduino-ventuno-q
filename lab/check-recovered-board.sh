#!/usr/bin/env bash
set -euo pipefail
echo '### Running system'
uname -a
cat /proc/sys/kernel/random/boot_id /proc/cmdline
echo '### GRUB after restoration'
sha256sum /boot/grub/grub.cfg /etc/default/grub
grub-editenv /boot/grub/grubenv list
echo '### Persistent crash records and test directory'
python3 - "${1:-47a1742d908043d0b5dd2ce8719afd20}" <<'PY'
from pathlib import Path
import re
import sys
trial = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', trial)
for name in ('/sys/fs/pstore', '/var/lib/systemd/pstore', '/var/lib/ventuno-trials/' + trial, '/boot/pantavisor-diagnostic/' + trial):
    path = Path(name)
    print(name)
    if not path.exists():
        print('(absent)')
        continue
    for f in sorted(path.iterdir()):
        print(f.name, f.stat().st_size, 'bytes')
PY
journalctl -u systemd-pstore --no-pager
echo '### Network and storage'
ip -br address
lsblk -dn -o NAME,SIZE,MODEL
echo '### Package integrity and failed units'
dpkg --audit
systemctl --failed --no-pager
echo '### Watchdog and clock after return'
cat /sys/class/watchdog/watchdog0/state
timedatectl status
