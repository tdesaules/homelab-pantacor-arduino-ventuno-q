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

identity = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', identity)
root = Path('/var/lib/ventuno-native-migrations') / identity
receipt = json.loads((root / 'migration.json').read_text())
manifest = json.loads((root / 'package/installation.json').read_text())
assert receipt['phase'] == 'native-selected'
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert Path('/boot/pantavisor/install-id').read_text().strip() == identity
assert not subprocess.check_output(['losetup', '-j', '/boot/pantavisor/pvstore.ext4'], text=True).strip()
for name in ('kernel', 'initramfs'):
    assert hashlib.sha256((Path('/boot/pantavisor') / name).read_bytes()).hexdigest() == manifest['files']['system/boot/pantavisor/' + name]
assert hashlib.sha256(Path('/boot/efi/EFI/ubuntu/grub.cfg').read_bytes()).hexdigest() == receipt['espSha256']
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-native-start', '/usr/bin/systemctl', 'reboot'], check=True)
print('Native platform boot scheduled:', identity, manifest['revision'])
PY
