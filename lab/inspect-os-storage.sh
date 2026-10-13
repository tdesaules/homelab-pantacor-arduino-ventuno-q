#!/usr/bin/env bash
# Read-only description of the storage actually used by this installation.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

assert Path('/boot/pantavisor/install-id').read_text().strip() == '6491b61ba229489cb8bacb1719de7c2c'
def output(*args): return subprocess.check_output(args, text=True).strip()
def filesystem(path):
    return dict(line.split('=', 1) for line in output('blkid', '-p', '-o', 'export', path).splitlines() if '=' in line)
root = json.loads(output('findmnt', '-J', '-o', 'SOURCE,FSTYPE,TARGET', '/'))['filesystems'][0]
print(json.dumps({'ubuntu_root': root,
    'pantavisor_store': filesystem('/boot/pantavisor/pvstore.ext4'),
    'nvme': filesystem('/dev/nvme0n1p1'),
    'store_size_bytes': Path('/boot/pantavisor/pvstore.ext4').stat().st_size,
    'emmc_partitions': output('lsblk', '-nr', '-o', 'TYPE', '/dev/mmcblk0').splitlines().count('part')}, indent=2))
PY
