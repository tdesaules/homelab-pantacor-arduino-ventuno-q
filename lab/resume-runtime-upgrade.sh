#!/usr/bin/env bash
# Resume native validation of the maintenance revision, from Ubuntu only.
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
assert re.fullmatch('[0-9a-f]{32}', install_id)
root = Path('/boot/pantavisor')
assert (root / 'install-id').read_text().strip() == install_id
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
record = json.loads((Path('/var/lib/ventuno-autonomous') / install_id / 'installation.json').read_text())
upgrade = record['runtime_upgrade']
assert hashlib.sha256((root / 'initramfs').read_bytes()).hexdigest() == upgrade['files']['initramfs']
assert not subprocess.check_output(['losetup', '-j', str(root / 'pvstore.ext4')], text=True).strip()
state = dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', str(root / 'state/grubenv'), 'list'], text=True).splitlines())
assert state['pv_rev'] == upgrade['revision'] and not state.get('pv_try')
subprocess.run(['grub-editenv', str(root / 'state/grubenv'), 'set', 'pv_rev=' + upgrade['previous_revision'], 'pv_try=' + upgrade['revision']], check=True)
subprocess.run(['grub-editenv', str(root / 'state/grubenv'), 'unset', 'ventuno_attempt'], check=True)
subprocess.run(['sync'], check=True)
print('Native try-boot validation armed; activate explicitly with start-autonomous.sh.')
PY
