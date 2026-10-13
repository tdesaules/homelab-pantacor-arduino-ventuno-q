#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

trial = sys.argv[1] if len(sys.argv) == 2 else ''
assert re.fullmatch('[0-9a-f]{32}', trial)
backup = Path('/var/lib/ventuno-trials') / trial
record = json.loads((backup / 'installation.json').read_text())
assert not (backup / 'started.json').exists(), 'This trial was already requested'
grub_env = dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines())
assert not any(grub_env.values()), f'Pending GRUB state: {grub_env}'
assert not subprocess.check_output(['dpkg', '--audit'], text=True).strip()
assert hashlib.sha256(Path('/boot/grub/grub.cfg').read_bytes()).hexdigest() == record['installed_grub_sha256']
assert re.search(r'^GRUB_DEFAULT=0$', Path('/etc/default/grub').read_text(), re.M)
directory = Path('/boot/pantavisor-diagnostic') / trial
for name, expected in record['files'].items():
    with (directory / name).open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
if record.get('runtime_storage'):
    image = directory / 'pvstore.ext4'
    assert image.is_file() and not image.is_symlink()
    assert image.stat().st_size == record['runtime_storage']['size']
    with image.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['runtime_storage']['sha256']
subprocess.run(['grub-reboot', record['entry_id']], check=True)
assert 'next_entry=' + record['entry_id'] in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines()
assert isinstance(record['return_seconds'], int) and 180 <= record['return_seconds'] <= 1800
state = {'trial_id': trial, 'before_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
         'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'return_seconds': record['return_seconds']}
(backup / 'started.json').write_text(json.dumps(state, indent=2) + '\n')
print(json.dumps(state, indent=2), flush=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-trial-' + trial[:12], '/usr/bin/systemctl', 'reboot'], check=True)
PY
