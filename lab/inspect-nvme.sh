#!/usr/bin/env bash
# Read-only inventory before the one-time application disk provisioning.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

device = '/dev/nvme0n1'
info = {
    'device': device,
    'model': Path('/sys/class/nvme/nvme0/model').read_text().strip(),
    'serial': Path('/sys/class/nvme/nvme0/serial').read_text().strip(),
    'serial_raw': Path('/sys/class/nvme/nvme0/serial').read_text(),
    'size_bytes': int(subprocess.check_output(['blockdev', '--getsize64', device], text=True)),
    'root_source': subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip(),
    'devices': json.loads(subprocess.check_output(['lsblk', '-b', '-J', '-o', 'NAME,PATH,TYPE,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS', device], text=True)),
    'signatures': json.loads(subprocess.check_output(['wipefs', '-n', '-J', device], text=True)),
    'swap': subprocess.check_output(['swapon', '--show', '--noheadings'], text=True),
    'holders': [p.name for p in Path('/sys/class/block/nvme0n1/holders').iterdir()],
}
print(json.dumps(info, indent=2))
PY
