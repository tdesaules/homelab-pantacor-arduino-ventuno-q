#!/usr/bin/env python3
"""Wait for the independent hardware rescue and preserve read-only evidence."""
import datetime
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'artifacts/native-hardware' / uuid.uuid4().hex
output.mkdir(parents=True, mode=0o700)
ssh = ['ssh', '-F', str(ROOT / 'artifacts/diagnostic-ssh/config'), '-o', 'ConnectTimeout=5',
       '-o', 'BatchMode=yes', 'ventuno-diagnostic']
deadline = time.monotonic() + 300
attempts = []
while time.monotonic() < deadline:
    try:
        probe = subprocess.run(ssh + ['test -f /run/ventuno-recovery && echo RECOVERY_READY'],
                               capture_output=True, text=True, timeout=10)
        attempts.append({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'exit': probe.returncode, 'stderr': probe.stderr})
        if probe.returncode == 0 and 'RECOVERY_READY' in probe.stdout: break
    except subprocess.TimeoutExpired:
        attempts.append({'timeout': True})
    time.sleep(5)
else:
    (output / 'attempts.json').write_text(json.dumps(attempts, indent=2))
    raise SystemExit('Rescue SSH timeout; evidence: ' + str(output))
(output / 'attempts.json').write_text(json.dumps(attempts, indent=2))
command = '''set -eu
test -f /run/ventuno-recovery
echo RECOVERY_READY
uname -a
cat /proc/cmdline /proc/uptime
echo PID1
cat /proc/1/comm
readlink /proc/1/exe
echo MOUNTS
cat /proc/mounts
if grep -E ' /mnt/(pv-system|appdata) |^/dev/(mmcblk|nvme)' /proc/mounts; then exit 3; fi
echo STORAGE_UNMOUNTED
echo BLOCKS
cat /proc/partitions
blkid /dev/mmcblk0p69 /dev/mmcblk0p71 /dev/nvme0n1p1
e2fsck -V
echo NETWORK
ip -4 addr
ip route
mkdir -p /sys/firmware/efi/efivars
if ! grep -q ' /sys/firmware/efi/efivars ' /proc/mounts; then
    mount -t efivarfs efivarfs /sys/firmware/efi/efivars
fi
test ! -e /sys/firmware/efi/efivars/BootNext-8be4df61-93ca-11d2-aa0d-00e098032b8c
echo BOOT_NEXT_CONSUMED
'''
result = subprocess.run(ssh + ['sh -s'], input=command, capture_output=True, text=True, timeout=60)
(output / 'inspection.txt').write_text(result.stdout + result.stderr)
print(result.stdout, result.stderr)
if result.returncode: raise SystemExit('Rescue inspection failed: ' + str(output))
variables = {}
for name in ('BootCurrent', 'BootOrder'):
    raw = subprocess.check_output(ssh + ['dd if=/sys/firmware/efi/efivars/' + name +
        '-8be4df61-93ca-11d2-aa0d-00e098032b8c bs=1 skip=4 2>/dev/null'], timeout=15)
    assert raw and len(raw) % 2 == 0
    variables[name] = [f'{int.from_bytes(raw[i:i+2], "little"):04X}' for i in range(0, len(raw), 2)]
(output / 'efi.json').write_text(json.dumps(variables, indent=2) + '\n')
print(variables)
log = subprocess.run(ssh + ['dmesg'], capture_output=True, text=True, timeout=30)
(output / 'dmesg.txt').write_text(log.stdout + log.stderr)
print('PASS: independent hardware rescue; evidence:', output)
