#!/usr/bin/env bash
# Read-only bootloader preflight and a user-readable copy for QEMU validation.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess

assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
assert 'GRUB_DEFAULT=0' in Path('/etc/default/grub').read_text().splitlines()
env = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
assert all(not line.split('=', 1)[1] for line in env.splitlines())
source = Path('/boot/efi/EFI/ubuntu/grubaa64.efi')
assert source.is_file()
assert Path('/boot/grub/arm64-efi/regexp.mod').exists()
directory = Path('/home/arduino/.cache/ventuno-grub-reference')
directory.mkdir(mode=0o700, exist_ok=True)
user = pwd.getpwnam('arduino')
os.chown(directory, user.pw_uid, user.pw_gid)
target = directory / source.name
if target.exists(): assert target.read_bytes() == source.read_bytes()
else: shutil.copyfile(source, target)
target.chmod(0o644)
modules = directory / 'arm64-efi.tar.gz'
subprocess.run(['tar', '-czf', str(modules), '-C', '/boot/grub', 'arm64-efi'], check=True)
modules.chmod(0o644)
record = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'modules_sha256': hashlib.sha256(modules.read_bytes()).hexdigest(),
          'grub_version': subprocess.check_output(['grub-install', '--version'], text=True).strip(),
          'root_uuid': subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '/'], text=True).strip(),
          'free_bytes': shutil.disk_usage('/').free,
          'grub_cfg_sha256': hashlib.sha256(Path('/boot/grub/grub.cfg').read_bytes()).hexdigest()}
(directory / 'reference.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
PY
