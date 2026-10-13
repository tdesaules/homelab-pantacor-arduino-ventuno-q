#!/usr/bin/env bash
# Restore the temporary GRUB change, then test BootNext with a listed EFI option.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

token = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', token)
directory = Path('/var/lib/ventuno-native-recovery') / token
record = json.loads((directory / 'trial.json').read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert sha('/boot/grub/grub.cfg') == record['chainGrubSha256']
assert sha(directory / 'grub.cfg.before') == record['grubSha256']
env = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
assert all(not line.split('=', 1)[1] for line in env.splitlines())
snippet = Path(record['snippet'])
assert snippet.name == '42_ventuno-native-recovery-' + token
assert record['chainEntry'] in snippet.read_text()
snippet.unlink()
shutil.copy2(directory / 'grub.cfg.before', '/boot/grub/grub.cfg')
subprocess.run(['grub-script-check', '/boot/grub/grub.cfg'], check=True)
before = subprocess.check_output(['efibootmgr'], text=True)
assert 'BootNext:' not in before
assert re.search(r'^BootOrder: (.+)$', before, re.M).group(1) == record['bootOrder']
assert sha(record['efi']) == record['efiSha256']
label = 'Ventuno recovery ' + token
assert label not in before
loader = '\\EFI\\ventuno-trial-' + token + '\\recoveryaa64.efi'
subprocess.run(['efibootmgr', '--create-only', '--disk', '/dev/mmcblk0', '--part', '69', '--label', label, '--loader', loader], check=True)
after = subprocess.check_output(['efibootmgr'], text=True)
entry = re.search(r'^Boot([0-9A-Fa-f]{4})\*? ' + re.escape(label) + r'\s', after, re.M).group(1)
record['orderedEntry'] = entry
(directory / 'trial.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['efibootmgr', '--bootorder', record['bootOrder'] + ',' + entry], check=True)
subprocess.run(['efibootmgr', '--bootnext', entry], check=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-rescue-ordered', '/usr/bin/systemctl', 'reboot'], check=True)
print('Original GRUB restored; Ubuntu first, rescue secondary, one-shot BootNext set.')
PY
