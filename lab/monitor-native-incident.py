#!/usr/bin/env python3
"""Capture live native health and kernel messages externally, without rebooting."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, default=1800)
args = parser.parse_args()
output = ROOT / 'artifacts/native-live' / uuid.uuid4().hex
output.mkdir(parents=True, mode=0o700)
print(output, flush=True)
ssh = ['ssh', '-F', str(ROOT / 'artifacts/diagnostic-ssh/config'), '-o', 'ConnectTimeout=3', 'ventuno-diagnostic']
command = '''echo CMDLINE; cat /proc/cmdline
echo UPTIME; cat /proc/uptime
echo BOOT_ID; cat /proc/sys/kernel/random/boot_id
echo GUARD; cat /trial-status/guard.status /trial-status/health.status
echo MEMORY; cat /proc/meminfo
echo PRESSURE; cat /proc/pressure/cpu /proc/pressure/io /proc/pressure/memory
echo CORE_CGROUP; cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.events
echo WATCHDOG
for name in identity bootstatus status state timeout timeleft; do
    printf '%s=' "$name"; cat /sys/class/watchdog/watchdog0/$name
done
echo TEMPERATURES
for zone in /sys/class/thermal/thermal_zone*; do cat "$zone/type" "$zone/temp"; done
echo KERNEL; dmesg
'''
start = time.monotonic()
native_seen = False
last_phase = None
count = 0
while time.monotonic() - start < args.seconds:
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        result = subprocess.run(ssh + [command], capture_output=True, timeout=12)
        text = result.stdout.decode(errors='replace')
        phase = 'native' if 'ventuno_install=' in text else 'recovery' if '(memdisk)/recovery/kernel' in text else 'unreachable'
        (output / f'{count:05d}.txt').write_text(stamp + '\n' + text + result.stderr.decode(errors='replace'))
    except subprocess.TimeoutExpired:
        phase = 'timeout'
        (output / f'{count:05d}.txt').write_text(stamp + '\nSSH timeout\n')
    if phase != last_phase:
        print(stamp, phase, flush=True)
        last_phase = phase
    if phase == 'native': native_seen = True
    count += 1
    if phase == 'recovery' and native_seen: break
    time.sleep(3)
(output / 'result.json').write_text(json.dumps({'samples': count, 'nativeObserved': native_seen,
    'finalPhase': last_phase, 'elapsedSeconds': time.monotonic() - start}, indent=2))
print('Capture finished:', output, flush=True)
