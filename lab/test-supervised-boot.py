#!/usr/bin/env python3
"""Boot the actual kernel/initramfs in QEMU, with and without a trace disk."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/prototype-1084-supervised')
args = parser.parse_args()
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
assert inputs.get('trial_supervisor_version') == 2
release = inputs['kernel_release']
trial = '0123456789abcdef0123456789abcdef'
logs = args.output_dir / 'qemu-tests'
logs.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory(dir=root / 'artifacts', prefix='qemu-trial-') as work:
    work = Path(work)
    fixture = work / 'fixture'
    marker = fixture / 'boot/pantavisor-diagnostic' / trial
    marker.mkdir(parents=True)
    (marker / 'trial-id').write_text(trial + '\n')
    (fixture / 'etc').mkdir()
    (fixture / 'etc/os-release').write_text('NAME="QEMU trace fixture"\n')
    disk = work / 'trace.ext4'
    with disk.open('wb') as f:
        f.truncate(128 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0',
                    '-d', str(fixture), str(disk)], check=True)
    for name, deadline, attach, pause in (('trace-disk', 45, True, False),
                                         ('missing-disk', 25, False, False),
                                         ('paused-supervisor', 15, False, True)):
        command = [
            'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
            '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio',
            '-monitor', 'none', '-nic', 'none', '-no-reboot',
            '-kernel', str(args.output_dir / f'vmlinuz-{release}'),
            '-initrd', str(args.output_dir / 'initramfs-ventuno-q.cpio.gz'),
            '-append', f'rdinit=/init console=ttyAMA0 loglevel=7 panic=5 ventuno_trial={trial} '
                       f'ventuno_trace_device=/dev/vda ventuno_return_seconds={deadline}'
                       + (' ventuno_test_pause=1' if pause else ''),
        ]
        if attach:
            command += ['-drive', f'file={disk},format=raw,if=virtio']
        start = time.monotonic()
        log = logs / f'{name}.log'
        with log.open('wb') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=deadline + 80)
        elapsed = time.monotonic() - start
        text = log.read_text(errors='replace')
        assert result.returncode == 0, f'{name}: QEMU exit {result.returncode}; see {log}'
        for message in ('SUPERVISOR_V2_STARTED', 'EARLY_MOUNTS_READY'):
            assert message in text, f'{name}: missing {message}; see {log}'
        assert 'Kernel panic' not in text, log
        if pause:
            assert 'FAULT_INJECTION_PAUSE_BEFORE_CHILDREN' in text
            assert 'RETURN_REQUESTED' not in text
            assert elapsed >= deadline + 10
        else:
            assert 'RETURN_REQUESTED' in text
        assert deadline <= elapsed < deadline + 70, elapsed
        if attach:
            diagnostic = subprocess.check_output(['debugfs', '-R', f'cat /boot/pantavisor-diagnostic/{trial}/trial.log', str(disk)], text=True)
            (logs / 'persistent-trace.log').write_text(diagnostic)
            assert 'BOOTSTRAP_STAGE=EARLY_LOG_READY' in diagnostic
            assert 'TRIAL_DIAGNOSTICS_COMPLETE=' + trial in diagnostic
            assert 'pantavisor_state=running' in diagnostic
        elif not pause:
            assert 'EARLY_LOG_MOUNT_FAILED' in text
            assert 'PANTAVISOR_CHILD_STARTED' not in text
        print(f'PASS: {name}, reboot observed after {elapsed:.1f}s (deadline {deadline}s)', flush=True)
