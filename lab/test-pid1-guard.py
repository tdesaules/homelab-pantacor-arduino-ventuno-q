#!/usr/bin/env python3
"""Prove that the independent guardian returns even if PID 1 stalls before exec."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-pid1')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs['pid1_runtime'] and inputs['trial_supervisor_version'] in (3, 4)
logs = output / 'qemu-pid1-guard-test'
logs.mkdir(exist_ok=True)
trial = '0123456789abcdef0123456789abcdef'
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-pid1-guard-') as work:
    work = Path(work)
    fixture = work / 'fixture'
    directory = fixture / 'boot/pantavisor-diagnostic' / trial
    directory.mkdir(parents=True)
    (directory / 'trial-id').write_text(trial + '\n')
    (fixture / 'etc').mkdir()
    (fixture / 'etc/os-release').write_text('NAME="PID1 guardian fault fixture"\n')
    disk = work / 'trace.ext4'
    with disk.open('wb') as stream: stream.truncate(128 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(fixture), str(disk)], check=True)
    command = [
        'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
        '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio', '-monitor', 'none',
        '-nic', 'none', '-no-reboot',
        '-kernel', str(output / ('vmlinuz-' + inputs['kernel_release'])),
        '-initrd', str(output / 'initramfs-ventuno-q.cpio.gz'),
        '-drive', f'file={disk},format=raw,if=virtio',
        '-append', f'rdinit=/init console=ttyAMA0 panic=5 ventuno_trial={trial} '
                   'ventuno_trace_device=/dev/vda ventuno_return_seconds=25 ventuno_pid1_test_stall=1',
    ]
    start = time.monotonic()
    with (logs / 'console.log').open('wb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True)
    elapsed = time.monotonic() - start
    text = (logs / 'console.log').read_text(errors='replace')
    assert 'PID1_GUARDIAN_ARMED' in text and 'PID1_BOOTSTRAP_STALLED' in text
    assert 'PID1_GUARDIAN_FALLBACK' in text and 'reboot: Restarting system' in text
    assert 'PANTAVISOR_PID1_HANDOFF' not in text and 'Kernel panic' not in text
    assert 25 <= elapsed < 85, elapsed
    subprocess.run(['e2fsck', '-f', '-n', str(disk)], check=True)
    print(f'PASS: independent guardian returned stalled PID 1 after {elapsed:.1f}s; support filesystem clean')
