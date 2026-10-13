#!/usr/bin/env python3
"""Shared prolonged-boot monitor and hardware CLI implementation."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from diagnostic_ssh import ROOT, ssh_command
from soak_validation import validate_snapshot

COMMAND = r'''set -eu
echo '### Kernel command line'
cat /proc/cmdline
echo '### Boot ID'
cat /proc/sys/kernel/random/boot_id
ventuno-revision-status
echo '### Uptime'
cat /proc/uptime
echo '### Memory'
cat /proc/meminfo
echo '### Storage'
df -Pk /data
echo '### Load'
cat /proc/loadavg
echo '### Thermal'
echo none
for path in /sys/class/thermal/thermal_zone*/temp; do
    [ -f "$path" ] || continue
    temperature=$(cat "$path" 2>/dev/null) || continue
    printf '%s %s\n' "$(cat "${path%/temp}/type")" "$temperature"
done
kernel=$(dmesg)
echo '### Kernel anomalies'
if faults=$(printf '%s\n' "$kernel" | grep -Ei 'Kernel panic|BUG:|Oops:|Out of memory:|oom-kill:|Killed process [0-9]|EXT4-fs error|Buffer I/O error|I/O error, dev|critical temperature reached'); then
    printf '%s\n' "$faults"
else
    [ "$?" -eq 1 ]
    echo none
fi
'''


def monitor(host, port, trial, inputs, directory, deadline, target, minimum, interval=15, require_watchdog=True):
    if not 5 <= interval <= 60 or not 0 < minimum < target <= deadline - 30:
        raise ValueError('Invalid observation window or sampling interval')
    if not inputs.get('pid1_runtime') or inputs.get('trial_supervisor_version') != 4:
        raise ValueError('A v4 PID 1 image is required')
    started = time.monotonic()
    samples = []
    result = {'trial_id': trial, 'deadline': deadline, 'target_elapsed': target, 'minimum_observation': minimum,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with (directory / 'soak-samples.jsonl').open('x') as stream:
            while time.monotonic() - started < deadline + 60:
                query_start = time.monotonic()
                reply = subprocess.run(ssh_command(host, port, command=COMMAND), capture_output=True, text=True, timeout=15)
                (directory / 'soak-latest.log').write_text(reply.stdout + reply.stderr)
                if reply.returncode:
                    raise RuntimeError('SSH snapshot failed: ' + reply.stderr)
                try:
                    sample = validate_snapshot(reply.stdout, trial, inputs, deadline, require_watchdog,
                                               samples[-1] if samples else None)
                except (ValueError, KeyError, IndexError, AttributeError):
                    # SSH starts just before core/app readiness at the first boot.
                    if not samples and time.monotonic() - started < 45:
                        time.sleep(2)
                        continue
                    raise
                sample['ssh_seconds'] = round(time.monotonic() - query_start, 3)
                sample['observed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                samples.append(sample)
                stream.write(json.dumps(sample, sort_keys=True) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
                print(f"sample={len(samples)} elapsed={sample['elapsed']}s heartbeat_lag={sample['heartbeat_lag']:.1f}s "
                      f"available={sample['mem_available_kib']}KiB store_free={sample['store_free_kib']}KiB", flush=True)
                if sample['elapsed'] >= target:
                    break
                time.sleep(min(interval, target - sample['elapsed']))
            else:
                raise RuntimeError('Observation exceeded the host-side timeout')
        duration = samples[-1]['elapsed'] - samples[0]['elapsed']
        if len(samples) < 3 or duration < minimum:
            raise RuntimeError(f'Insufficient observation: {len(samples)} samples over {duration}s')
        peaks = {}
        for sample in samples:
            for name, value in sample['temperatures_millicelsius'].items():
                peaks[name] = max(peaks.get(name, value), value)
        result.update(status='passed', samples=len(samples), observation_seconds=duration,
                      first_elapsed=samples[0]['elapsed'], last_elapsed=samples[-1]['elapsed'],
                      boot_id=samples[0]['boot_id'], guardian_pid=samples[0]['guardian_pid'],
                      min_mem_available_kib=min(s['mem_available_kib'] for s in samples),
                      min_store_free_kib=min(s['store_free_kib'] for s in samples),
                      max_heartbeat_lag=max(s['heartbeat_lag'] for s in samples),
                      max_ssh_seconds=max(s['ssh_seconds'] for s in samples),
                      peak_temperatures_millicelsius=peaks,
                      core_starts=1, application_starts=1, final_snapshot=samples[-1])
    except BaseException as error:
        result.update(status='failed', error=str(error), samples=len(samples))
        raise
    finally:
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        temporary = directory / 'soak-result.json.tmp'
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(directory / 'soak-result.json')
    print('PASS: uninterrupted core/application stability window completed', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial-id', required=True)
    parser.add_argument('--host', default='192.168.1.20')
    parser.add_argument('--interval', type=int, default=15)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--detach', action='store_true')
    mode.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.trial_id):
        raise SystemExit('Invalid trial ID')
    directory = ROOT / 'artifacts/trials' / args.trial_id
    inputs = json.loads((directory / 'build-inputs.json').read_text())
    deadline = inputs['trial_return_seconds']
    if not 600 <= deadline <= 1800:
        raise SystemExit('Hardware prolonged qualification requires a 600..1800 second trial')
    if args.wait:
        stop = time.monotonic() + deadline + 120
        while not (directory / 'soak-result.json').exists() and time.monotonic() < stop:
            time.sleep(5)
        result = json.loads((directory / 'soak-result.json').read_text())
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['status'] == 'passed' else 1)
    if (directory / 'soak-samples.jsonl').exists() or (directory / 'soak-result.json').exists():
        raise SystemExit('Existing observation evidence: refusing to overwrite it')
    if args.detach:
        with (directory / 'soak-monitor.log').open('x') as log:
            command = [sys.executable, str(Path(__file__).resolve()), '--trial-id', args.trial_id,
                       '--host', args.host, '--interval', str(args.interval)]
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'Monitor PID {child.pid}; log: {directory / "soak-monitor.log"}')
        return
    monitor(args.host, 2222, args.trial_id, inputs, directory, deadline, deadline - 50, deadline - 150, args.interval)


if __name__ == '__main__':
    main()
