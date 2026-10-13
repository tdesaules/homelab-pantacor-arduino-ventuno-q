#!/usr/bin/env bash
# Journal replay only on an unmounted, regular lab image, with a backup first.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

trial = sys.argv[1] if len(sys.argv) == 2 else ''
assert re.fullmatch('[0-9a-f]{32}', trial)
assert Path('/proc/1/comm').read_text().strip() == 'systemd'
directory = Path('/boot/pantavisor-diagnostic') / trial
image = directory / 'pvstore.ext4'
assert stat.S_ISREG(image.lstat().st_mode) and image.stat().st_size == 256 * 1024 * 1024
assert not subprocess.check_output(['losetup', '-j', str(image)], text=True).strip()
backup = directory / 'pvstore.before-journal-replay.ext4'
assert not backup.exists()
shutil.copy2(image, backup)
backup.chmod(0o600)
subprocess.run(['sync'], check=True)
result = subprocess.run(['e2fsck', '-p', str(image)])
assert result.returncode in (0, 1), result.returncode
subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)
for path in ('/disks/perm/diagnostic/data/boots', '/disks/perm/diagnostic/data/heartbeat.json'):
    subprocess.run(['debugfs', '-R', 'cat ' + path, str(image)], check=True)
print('Journal replay completed; untouched pre-replay copy:', backup)
PY
systemctl --failed --no-pager
