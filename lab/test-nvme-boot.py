#!/usr/bin/env python3
"""Verify two boots on one application disk, plus absent/wrong UUID disks, in QEMU."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from diagnostic_ssh import ROOT, ssh_command
from nvme_validation import validate_nvme

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-nvme')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs['pid1_runtime'] and inputs['app_storage']
profile = inputs['app_storage']
logs = output / 'qemu-nvme-test' / uuid.uuid4().hex
logs.mkdir(parents=True)

def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def fsck(path):
    subprocess.run(['e2fsck', '-f', '-n', str(path)], check=True)

def read(image, path):
    return subprocess.check_output(['debugfs', '-R', 'cat ' + path, str(image)], stderr=subprocess.DEVNULL, text=True).strip()

def partition_view(disk, destination):
    with disk.open('rb') as source, destination.open('wb') as target:
        source.seek(1024 * 1024)
        remaining = 128 * 1024 * 1024
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            assert chunk
            target.write(chunk)
            remaining -= len(chunk)
    return destination

with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-nvme-') as work:
    work = Path(work)
    app_fixture = work / 'application'
    (app_fixture / 'perm/diagnostic/data').mkdir(parents=True)
    (app_fixture / '.ventuno-app-storage').write_text('ventuno-appdata-v1 ' + profile['filesystem_uuid'] + '\n')
    disks = {}
    for name, fs_uuid in (('data', profile['filesystem_uuid']), ('wrong-uuid', str(uuid.uuid4()))):
        filesystem = work / (name + '.ext4')
        with filesystem.open('wb') as stream: stream.truncate(128 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-U', fs_uuid, '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(app_fixture), str(filesystem)], check=True)
        disk = work / (name + '.gpt')
        with disk.open('wb') as stream: stream.truncate(130 * 1024 * 1024)
        layout = f"label: gpt\nlabel-id: {profile['disk_guid']}\n\nstart=2048, size=262144, type=linux, uuid={profile['partition_uuid']}\n"
        subprocess.run(['sfdisk', '--quiet', str(disk)], input=layout, text=True, check=True)
        with filesystem.open('rb') as source, disk.open('r+b') as target:
            target.seek(1024 * 1024)
            shutil.copyfileobj(source, target)
        disks[name] = disk
    wrong_before = digest(disks['wrong-uuid'])
    identity = None
    for name, expected, attached in (('first', 1, 'data'), ('second', 2, 'data'), ('missing', 0, None), ('wrong-uuid', 0, 'wrong-uuid')):
        case_logs = logs / name
        case_logs.mkdir()
        trial = uuid.uuid4().hex
        fixture = work / ('fixture-' + name)
        directory = fixture / 'boot/pantavisor-diagnostic' / trial
        directory.mkdir(parents=True)
        (directory / 'trial-id').write_text(trial + '\n')
        shutil.copyfile(output / 'pvstore.ext4', directory / 'pvstore.ext4')
        (fixture / 'etc').mkdir()
        (fixture / 'etc/os-release').write_text('NAME="NVMe persistence QEMU fixture"\n')
        support = work / ('support-' + name + '.ext4')
        with support.open('wb') as stream: stream.truncate(512 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(fixture), str(support)], check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        deadline = 110 if expected else 90
        command = [
            'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
            '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot',
            '-kernel', str(output / ('vmlinuz-' + inputs['kernel_release'])), '-initrd', str(output / 'initramfs-ventuno-q.cpio.gz'),
            '-drive', f'file={support},format=raw,if=virtio',
            '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:2222', '-device', 'virtio-net-pci,netdev=net0',
            '-append', f'rdinit=/init console=ttyAMA0 panic=5 ventuno_trial={trial} '
                       f'ventuno_trace_device=/dev/vda ventuno_return_seconds={deadline}',
        ]
        if attached:
            command += ['-drive', f'file={disks[attached]},format=raw,if=none,id=appdisk',
                        '-device', f"nvme,drive=appdisk,serial={profile['serial']}"]
        after = case_logs / 'pvstore-after.ext4'
        with (case_logs / 'console.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                if expected:
                    until = time.monotonic() + 65
                    while time.monotonic() < until:
                        reply = subprocess.run(ssh_command('127.0.0.1', port, command='cat /proc/cmdline; ventuno-revision-status'), capture_output=True, text=True, timeout=10)
                        (case_logs / 'runtime.log').write_text(reply.stdout + reply.stderr)
                        try:
                            if reply.returncode or 'ventuno_trial=' + trial not in reply.stdout:
                                raise ValueError('SSH not ready')
                            result = validate_nvme(reply.stdout, inputs, expected, identity)
                            assert result['device'] == '/dev/nvme0n1p1'
                            identity = result['application_identity']
                            (case_logs / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
                            break
                        except (ValueError, KeyError, IndexError):
                            if process.poll() is not None: raise RuntimeError('Guest exited before NVMe validation')
                            time.sleep(2)
                    else: raise RuntimeError('NVMe runtime validation failed: ' + str(case_logs))
                assert process.wait(timeout=deadline + 35) == 0
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                subprocess.run(['debugfs', '-R', f'dump /boot/pantavisor-diagnostic/{trial}/pvstore.ext4 {after}', str(support)], check=True)
        console = (case_logs / 'console.log').read_text(errors='replace')
        trace = read(support, f'/boot/pantavisor-diagnostic/{trial}/trial.log')
        (case_logs / 'persistent-trace.log').write_text(trace)
        assert 'Kernel panic' not in console
        fsck(support)
        fsck(after)
        fallback = subprocess.check_output(['debugfs', '-R', 'stat /disks/perm/diagnostic/data', str(after)], stderr=subprocess.DEVNULL, text=True)
        assert 'Inode:' not in fallback
        if expected:
            assert 'PANTAVISOR_NATIVE_SHUTDOWN_COMPLETE=1' in console and 'PID1_GUARDIAN_FALLBACK' not in console
            assert 'APPDATA_UUID=' + profile['filesystem_uuid'] in trace
            assert 'APPDATA_CLEANLY_UNMOUNTED=1' in trace and 'RUNTIME_CLEANUP_UNMOUNT_FAILURES=0' in trace
            data = partition_view(disks['data'], case_logs / 'application-after.ext4')
            fsck(data)
            assert read(data, '/perm/diagnostic/data/boots') == str(expected)
            assert read(data, '/perm/diagnostic/data/identity') == identity
            assert read(after, '/disks/perm/core/data/boots') == '1'
            print(f'PASS: {name} full boot, NVMe counter={expected}, same application identity; all filesystems clean', flush=True)
        else:
            assert 'APPDATA_REQUIRED_UNAVAILABLE=1' in console and 'PID1_GUARDIAN_FALLBACK' in console
            assert 'APPDATA_UUID_NOT_FOUND' in trace
            assert digest(after) == inputs['runtime_storage']['sha256'], 'Store changed despite missing application disk'
            assert digest(disks['wrong-uuid']) == wrong_before, 'Unrelated disk was modified'
            print(f'PASS: {name}, bounded return, no application fallback and no disk formatting', flush=True)
    partition_view(disks['data'], logs / 'application-after.ext4')
print('NVMe integration evidence:', logs)
