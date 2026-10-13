#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

trial = sys.argv[1] if len(sys.argv) == 2 else ''
if not re.fullmatch('[0-9a-f]{32}', trial):
    raise SystemExit('Expected a trial ID')
stage = Path('/home/arduino/.cache/ventuno-trial-' + trial)
request = json.loads((stage / 'request.json').read_text())
assert request['trial_id'] == trial
assert request['entry_id'] == 'pantavisor-trial-' + trial
release = subprocess.check_output(['uname', '-r'], text=True).strip()
assert request['kernel_release'] == release
assert subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '/'], text=True).strip() == request['rootfs_uuid']
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
assert not subprocess.check_output(['dpkg', '--audit'], text=True).strip()
grub_env = dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines())
assert not any(grub_env.values()), f'Pending GRUB state: {grub_env}'
defaults = Path('/etc/default/grub').read_text()
assert re.search(r'^GRUB_DEFAULT=0$', defaults, re.M)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

names = {f'vmlinuz-{release}', 'initramfs-ventuno-q.cpio.gz', 'grub-diagnostic.cfg', 'trial-id', 'build-inputs.json'}
inputs = json.loads((stage / 'build-inputs.json').read_text())
if inputs.get('embedded_runtime'):
    names.add('pvstore.ext4.gz')
assert set(request['files']) == names
for name in names:
    assert not (stage / name).is_symlink()
    assert sha(stage / name) == request['files'][name], name
assert (stage / 'trial-id').read_text().strip() == trial
assert inputs['bounded_trial'] and inputs.get('trial_supervisor_version') in ((3, 4) if inputs.get('pid1_runtime') else (2,))
maximum = min(inputs.get('trial_max_seconds', 180), 1800) if inputs.get('trial_supervisor_version') == 4 else 180
assert isinstance(request['return_seconds'], int) and 180 <= request['return_seconds'] <= maximum
assert request['return_seconds'] == inputs.get('trial_return_seconds', 180)
if inputs.get('trial_supervisor_version') == 4:
    assert f"ventuno_return_seconds={request['return_seconds']}" in (stage / 'grub-diagnostic.cfg').read_text().split()
revision = inputs.get('boot_revision', '0')
    # Same safe subset as lab/revision_names.py; standalone remote script.
    assert re.fullmatch(r'0|locals/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', revision)
if 'boot_revision' in inputs:
    assert request['boot_revision'] == revision
    assert 'pv_rev=' + revision in (stage / 'grub-diagnostic.cfg').read_text().split()
subprocess.run(['grub-script-check', str(stage / 'grub-diagnostic.cfg')], check=True)
backup = Path('/var/lib/ventuno-trials') / trial
backup.mkdir(parents=True, exist_ok=False)
for source, name in (('/boot/grub/grub.cfg', 'grub.cfg.before'),
                     ('/boot/grub/grubenv', 'grubenv.before'),
                     ('/etc/default/grub', 'default-grub.before')):
    shutil.copy2(source, backup / name)
destination = Path('/boot/pantavisor-diagnostic') / trial
destination.mkdir(parents=True, exist_ok=False)
for name in names:
    shutil.copyfile(stage / name, destination / name)
    (destination / name).chmod(0o600)
if inputs.get('embedded_runtime'):
    storage = inputs['runtime_storage']
    assert storage['size'] == 256 * 1024 * 1024
    assert shutil.disk_usage('/').free > storage['size'] + 512 * 1024 * 1024
    image = destination / 'pvstore.ext4'
    with gzip.open(destination / 'pvstore.ext4.gz', 'rb') as source, image.open('xb') as target:
        copied = 0
        while chunk := source.read(1024 * 1024):
            copied += len(chunk)
            assert copied <= storage['size']
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    image.chmod(0o600)
    assert copied == storage['size'] and sha(image) == storage['sha256']
snippet = Path('/etc/grub.d') / ('41_ventuno_trial_' + trial)
body = "#!/bin/sh\ncat <<'VENTUNO_TRIAL_EOF'\n" + (stage / 'grub-diagnostic.cfg').read_text() + 'VENTUNO_TRIAL_EOF\n'
with snippet.open('x') as f:
    f.write(body)
snippet.chmod(0o755)
candidate = backup / 'grub.cfg.candidate'
try:
    generated = subprocess.run(['grub-mkconfig', '-o', str(candidate)], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (backup / 'grub-mkconfig.log').write_text(generated.stdout)
    if generated.returncode:
        print(generated.stdout)
        generated.check_returncode()
    print('GRUB generation log:', backup / 'grub-mkconfig.log')
    subprocess.run(['grub-script-check', str(candidate)], check=True)
    cfg = candidate.read_text()
    first = next(line for line in cfg.splitlines() if line.startswith('menuentry '))
    assert first.startswith("menuentry 'Ubuntu'")
    assert 'set default="0"' in cfg
    assert 'save_env next_entry' in cfg
    assert ('--id ' + request['entry_id']) in cfg
    assert f'ventuno_trial={trial}' in cfg
    os.replace(candidate, '/boot/grub/grub.cfg')
except BaseException:
    snippet.unlink()
    raise
record = request | {'runtime_storage': inputs.get('runtime_storage'),
                    'installed_grub_sha256': sha(Path('/boot/grub/grub.cfg')),
                    'before_grub_sha256': sha(backup / 'grub.cfg.before'),
                    'before_defaults_sha256': sha(backup / 'default-grub.before'),
                    'snippet_sha256': sha(snippet), 'ubuntu_default_preserved': True}
(backup / 'installation.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['sync'], check=True)
print(json.dumps(record, indent=2))
print('Installed only. No next_entry set; no reboot scheduled.')
PY
