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

token = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', token)
record = json.loads((Path('/var/lib/ventuno-native-recovery') / token / 'trial.json').read_text())
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
for path, key in ((record['efi'], 'efiSha256'), ('/boot/grub/grub.cfg', 'grubSha256'),
                  ('/boot/pantavisor/kernel', 'kernelSha256'), ('/boot/pantavisor/initramfs', 'initramfsSha256')):
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == record[key]
current = subprocess.check_output(['efibootmgr'], text=True)
assert 'BootNext:' not in current
assert re.search(r'^BootOrder: (.+)$', current, re.M).group(1) == record['bootOrder']
assert 'ventuno_recovery=1' in subprocess.check_output(['grub-editenv', '/boot/pantavisor/state/boot-budget', 'list'], text=True)
subprocess.run(['efibootmgr', '--bootnext', record['entry']], check=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-native-recovery-test', '/usr/bin/systemctl', 'reboot'], check=True)
print('One-shot direct UEFI rescue scheduled; BootOrder remains', record['bootOrder'])
PY
