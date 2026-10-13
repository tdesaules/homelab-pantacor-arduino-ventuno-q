#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

def read(path):
    return Path(path).read_text().strip()

firmware = []
for path in Path('/proc/device-tree').rglob('firmware-name'):
    firmware.append({'node': str(path), 'names': path.read_bytes().rstrip(b'\0').decode().split('\0')})
remoteproc = []
for path in sorted(Path('/sys/class/remoteproc').glob('remoteproc*')):
    remoteproc.append({key: read(path / key) for key in ('name', 'state', 'firmware')})
uart = Path('/sys/class/tty/ttyMSM0/device')
print(json.dumps({
    'kernel_release': subprocess.check_output(['uname', '-r'], text=True).strip(),
    'loaded_modules': sorted(line.split()[0] for line in read('/proc/modules').splitlines()),
    'device_tree_firmware': firmware,
    'remoteproc': remoteproc,
    'uart_device': str(uart.resolve()),
    'uart_of_node': str((uart / 'of_node').resolve()),
    'cmdline': read('/proc/cmdline'),
    'grub_environment': subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True),
}, indent=2))
PY
