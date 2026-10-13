#!/usr/bin/env bash
# Restore the exact ESP bootstrap after the one-shot independent rescue test.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

token = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', token)
directory = Path('/var/lib/ventuno-native-recovery') / token
record = json.loads((directory / 'trial.json').read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert 'BOOT_IMAGE=/boot/vmlinuz-' in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
target = Path('/boot/efi/EFI/ubuntu/grub.cfg')
backup = directory / 'esp-grub.cfg.before'
assert sha(target) == record['espBootstrapTrial']
assert sha(backup) == record['espBootstrapBefore']
assert 'native_trial=0\n' in Path(record['onceEnv']).read_text()
assert sha('/boot/grub/grub.cfg') == record['grubSha256']
assert sha('/boot/pantavisor/kernel') == record['kernelSha256']
assert sha('/boot/pantavisor/initramfs') == record['initramfsSha256']
efi = subprocess.check_output(['efibootmgr'], text=True)
assert 'BootNext:' not in efi
assert re.search(r'^BootOrder: (.+)$', efi, re.M).group(1) == record['bootOrder']
temporary = target.with_name('grub.cfg.restore')
with temporary.open('xb') as stream:
    stream.write(backup.read_bytes()); stream.flush(); os.fsync(stream.fileno())
temporary.replace(target)
subprocess.run(['sync'], check=True)
assert sha(target) == record['espBootstrapBefore']
record['espOnlyTrialPassed'] = True
record['factoryBootstrapRestored'] = True
(directory / 'trial.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
PY
