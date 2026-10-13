#!/usr/bin/env bash
# Install a dedicated rescue EFI and create an inactive UEFI entry.
# Does not overwrite the runtime/store, change BootOrder, select BootNext or reboot.
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

token, expected = sys.argv[1:]
assert re.fullmatch('[0-9a-f]{32}', token)
assert re.fullmatch('[0-9a-f]{64}', expected)
def run(*args): return subprocess.check_output(args, text=True).strip()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert run('findmnt', '-n', '-o', 'SOURCE', '/') == '/dev/mmcblk0p71'
assert run('findmnt', '-n', '-o', 'SOURCE', '/boot/efi') == '/dev/mmcblk0p69'
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert 'ventuno_recovery=1' in run('grub-editenv', '/boot/pantavisor/state/boot-budget', 'list')
assert not any(line.startswith('next_entry=') and line.split('=', 1)[1] for line in run('grub-editenv', '/boot/grub/grubenv', 'list').splitlines())
secure = list(Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))
assert len(secure) == 1 and secure[0].read_bytes()[4] == 0, 'Unsigned rescue requires Secure Boot disabled'
source = Path('/home/arduino/.cache') / ('ventuno-native-' + token) / 'recoveryaa64.efi'
assert source.is_file() and not source.is_symlink() and sha(source) == expected
assert shutil.disk_usage('/boot/efi').free > source.stat().st_size + 16 * 1024**2
record = Path('/var/lib/ventuno-native-recovery') / token
record.mkdir(parents=True, mode=0o700, exist_ok=False)
before = run('efibootmgr', '-v')
assert 'BootNext:' not in before
order = re.search(r'^BootOrder: (.+)$', before, re.M).group(1)
(record / 'efi-before.txt').write_text(before + '\n')
destination = Path('/boot/efi/EFI') / ('ventuno-trial-' + token)
destination.mkdir(exist_ok=False)
shutil.copyfile(source, destination / 'recoveryaa64.efi')
assert sha(destination / 'recoveryaa64.efi') == expected
label = 'Ventuno recovery ' + token
subprocess.run(['efibootmgr', '--create-only', '--disk', '/dev/mmcblk0', '--part', '69',
                '--label', label, '--loader', '\\EFI\\' + destination.name + '\\recoveryaa64.efi'], check=True)
after = run('efibootmgr', '-v')
assert re.search(r'^BootOrder: (.+)$', after, re.M).group(1) == order
entry = re.search(r'^Boot([0-9A-Fa-f]{4})\*? ' + re.escape(label) + r'\s', after, re.M).group(1)
data = {'token': token, 'entry': entry, 'bootOrder': order, 'efi': str(destination / 'recoveryaa64.efi'),
        'efiSha256': expected, 'grubSha256': sha('/boot/grub/grub.cfg'),
        'installId': Path('/boot/pantavisor/install-id').read_text().strip(),
        'kernelSha256': sha('/boot/pantavisor/kernel'), 'initramfsSha256': sha('/boot/pantavisor/initramfs')}
(record / 'trial.json').write_text(json.dumps(data, indent=2) + '\n')
subprocess.run(['sync'], check=True)
print(json.dumps(data, indent=2))
PY
