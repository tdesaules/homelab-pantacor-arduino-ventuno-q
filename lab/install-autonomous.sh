#!/usr/bin/env bash
# Install a durable file-backed store and a stable GRUB menu entry; keep Ubuntu default.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

install_id = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', install_id)
stage = Path('/home/arduino/.cache/ventuno-autonomous-' + install_id)
request = json.loads((stage / 'request.json').read_text())
inputs = json.loads((stage / 'build-inputs.json').read_text())
assert request['install_id'] == install_id
assert inputs['autonomous_boot'] and not inputs['bounded_trial'] and inputs['trial_supervisor_version'] == 5
assert inputs['runtime_storage']['size'] == 1024 * 1024 * 1024
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
assert subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '/'], text=True).strip() == request['root_uuid']
assert subprocess.check_output(['uname', '-r'], text=True).strip() == inputs['kernel_release']
assert not subprocess.check_output(['dpkg', '--audit'], text=True).strip()
assert re.search(r'^GRUB_DEFAULT=0$', Path('/etc/default/grub').read_text(), re.M)
grub_env = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
assert not Path('/boot/grub/grubenv').is_symlink() and Path('/boot/grub/grubenv').stat().st_size == 1024
assert all(not line.split('=', 1)[1] for line in grub_env.splitlines())
assert shutil.disk_usage('/').free > 3 * 1024 * 1024 * 1024
device = Path('/dev/disk/by-uuid') / inputs['app_storage']['filesystem_uuid']
assert device.resolve() == Path('/dev/nvme0n1p1')
assert Path('/sys/class/nvme/nvme0/serial').read_text().strip() == inputs['app_storage']['serial']
assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(device)], text=True).strip()
identity = subprocess.check_output(['debugfs', '-R', 'cat /perm/diagnostic/data/identity', str(device)], stderr=subprocess.DEVNULL, text=True).strip()
counter = subprocess.check_output(['debugfs', '-R', 'cat /perm/diagnostic/data/boots', str(device)], stderr=subprocess.DEVNULL, text=True).strip()
if counter: assert counter.isdigit() and identity

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

assert set(request['files']) == {'kernel', 'initramfs', 'pvstore.ext4.gz', 'grubenv', 'install-id', 'build-inputs.json', 'grub-entry.cfg'}
for name, digest in request['files'].items():
    assert not (stage / name).is_symlink() and sha(stage / name) == digest
assert (stage / 'install-id').read_text().strip() == install_id
subprocess.run(['grub-script-check', str(stage / 'grub-entry.cfg')], check=True)
root = Path('/boot/pantavisor')
assert not root.exists(), 'Existing durable store: refusing overwrite'
backup = Path('/var/lib/ventuno-autonomous') / install_id
backup.mkdir(parents=True, mode=0o700, exist_ok=False)
for source, name in (('/boot/grub/grub.cfg', 'grub.cfg.before'), ('/boot/grub/grubenv', 'grubenv.before'), ('/etc/default/grub', 'defaults.before')):
    shutil.copy2(source, backup / name)
root.mkdir(mode=0o700)
(root / 'state').mkdir(mode=0o700)
(root / 'logs').mkdir(mode=0o700)
for name in ('kernel', 'initramfs', 'install-id', 'build-inputs.json'):
    shutil.copyfile(stage / name, root / name)
    (root / name).chmod(0o600)
shutil.copyfile(stage / 'grubenv', root / 'state/grubenv')
(root / 'state/grubenv').chmod(0o600)
subprocess.run(['grub-editenv', str(root / 'state/boot-budget'), 'create'], check=True)
subprocess.run(['grub-editenv', str(root / 'state/boot-budget'), 'set', 'ventuno_boots=0'], check=True)
store = root / 'pvstore.ext4'
with gzip.open(stage / 'pvstore.ext4.gz', 'rb') as source, store.open('xb') as target:
    copied = 0
    while chunk := source.read(1024 * 1024):
        copied += len(chunk)
        assert copied <= inputs['runtime_storage']['size']
        target.write(chunk)
    target.flush(); os.fsync(target.fileno())
store.chmod(0o600)
assert copied == inputs['runtime_storage']['size'] and sha(store) == inputs['runtime_storage']['sha256']
subprocess.run(['e2fsck', '-f', '-n', str(store)], check=True)
snippet = Path('/etc/grub.d/41_ventuno_persistent')
assert not snippet.exists()
snippet.write_text("#!/bin/sh\ncat <<'VENTUNO_EOF'\n" + (stage / 'grub-entry.cfg').read_text() + 'VENTUNO_EOF\n')
snippet.chmod(0o755)
candidate = backup / 'grub.cfg.candidate'
try:
    generated = subprocess.run(['grub-mkconfig', '-o', str(candidate)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (backup / 'grub-mkconfig.log').write_text(generated.stdout)
    generated.check_returncode()
    subprocess.run(['grub-script-check', str(candidate)], check=True)
    config = candidate.read_text()
    assert next(line for line in config.splitlines() if line.startswith('menuentry ')).startswith("menuentry 'Ubuntu'")
    assert 'set default="0"' in config and '--id pantavisor-persistent' in config
    os.replace(candidate, '/boot/grub/grub.cfg')
except BaseException:
    snippet.unlink()
    raise
record = request | {'installed_grub_sha256': sha(Path('/boot/grub/grub.cfg')),
                    'before_grub_sha256': sha(backup / 'grub.cfg.before'),
                    'defaults_sha256': sha(Path('/etc/default/grub')), 'snippet_sha256': sha(snippet),
                    'store_inode': store.stat().st_ino, 'store_size': store.stat().st_size,
                    'store_uuid': subprocess.check_output(['blkid', '-p', '-s', 'UUID', '-o', 'value', str(store)], text=True).strip(),
                    'previous_application_identity': identity or None, 'previous_application_starts': int(counter or 0),
                    'ubuntu_default_preserved': True}
(backup / 'installation.json').write_text(json.dumps(record, indent=2) + '\n')
(stage / 'installed.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['sync'], check=True)
print(json.dumps(record, indent=2))
print('Installed. Ubuntu remains default; no reboot scheduled.')
PY
