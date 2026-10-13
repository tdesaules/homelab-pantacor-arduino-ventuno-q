#!/usr/bin/env python3
"""Exercise the prolonged deadline and stability monitor in a four-minute QEMU boot."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from diagnostic_ssh import ROOT, ssh_command
from soak_monitor import monitor

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-soak')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs['pid1_runtime'] and inputs['trial_supervisor_version'] == 4
trial = uuid.uuid4().hex
logs = output / 'qemu-soak-test' / trial
logs.mkdir(parents=True)
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-soak-') as work:
    work = Path(work)
    fixture = work / 'fixture'
    directory = fixture / 'boot/pantavisor-diagnostic' / trial
    directory.mkdir(parents=True)
    (directory / 'trial-id').write_text(trial + '\n')
    shutil.copyfile(output / 'pvstore.ext4', directory / 'pvstore.ext4')
    (fixture / 'etc').mkdir()
    (fixture / 'etc/os-release').write_text('NAME="Prolonged boot QEMU fixture"\n')
    disk = work / 'trace.ext4'
    with disk.open('wb') as stream: stream.truncate(512 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(fixture), str(disk)], check=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [
        'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
        '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot',
        '-kernel', str(output / ('vmlinuz-' + inputs['kernel_release'])),
        '-initrd', str(output / 'initramfs-ventuno-q.cpio.gz'),
        '-drive', f'file={disk},format=raw,if=virtio',
        '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:2222', '-device', 'virtio-net-pci,netdev=net0',
        '-append', f'rdinit=/init console=ttyAMA0 panic=5 ventuno_trial={trial} '
                   'ventuno_trace_device=/dev/vda ventuno_return_seconds=240',
    ]
    with (logs / 'console.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                reply = subprocess.run(ssh_command('127.0.0.1', port), capture_output=True, text=True, timeout=10)
                if reply.returncode == 0 and 'DHCP_BOUND=1' in reply.stdout: break
                if process.poll() is not None: raise RuntimeError('Guest exited before SSH')
                time.sleep(2)
            else: raise RuntimeError('SSH did not become available')
            monitor('127.0.0.1', port, trial, inputs, logs, 240, 200, 150, require_watchdog=False)
            assert process.wait(timeout=90) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            subprocess.run(['debugfs', '-R', f'dump /boot/pantavisor-diagnostic/{trial}/pvstore.ext4 {logs / "pvstore-after.ext4"}', str(disk)], check=True)
    console = (logs / 'console.log').read_text(errors='replace')
    assert 'PANTAVISOR_NATIVE_SHUTDOWN_COMPLETE=1' in console
    assert 'PID1_GUARDIAN_FALLBACK' not in console and 'Kernel panic' not in console
    trace = subprocess.check_output(['debugfs', '-R', f'cat /boot/pantavisor-diagnostic/{trial}/trial.log', str(disk)], text=True)
    (logs / 'persistent-trace.log').write_text(trace)
    assert 'PANTAVISOR_STORAGE_UNMOUNTED=1' in trace and 'RUNTIME_CLEANUP_UNMOUNT_FAILURES=0' in trace
    subprocess.run(['e2fsck', '-f', '-n', str(disk)], check=True)
    subprocess.run(['e2fsck', '-f', '-n', str(logs / 'pvstore-after.ext4')], check=True)
    for container in ('core', 'diagnostic'):
        counter = subprocess.check_output(['debugfs', '-R', f'cat /disks/perm/{container}/data/boots', str(logs / 'pvstore-after.ext4')], text=True).strip()
        assert counter == '1', (container, counter)
    print('PASS: extended deadline, stability monitor, native shutdown and unchanged persistent counters; logs:', logs)
