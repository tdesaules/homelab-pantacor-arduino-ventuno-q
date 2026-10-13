#!/usr/bin/env python3
"""Three QEMU boots: hot updates, commit to DONE, failed readiness and rollback recovery."""
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
from local_updates import Session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-updates')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
profile = inputs['app_storage']
logs = output / 'qemu-updates-test' / uuid.uuid4().hex
logs.mkdir(parents=True)

def fsck(image): subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)
def read(image, path): return subprocess.check_output(['debugfs', '-R', 'cat ' + path, str(image)], stderr=subprocess.DEVNULL, text=True).strip()

with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-updates-') as work:
    work = Path(work)
    app_fixture = work / 'app-fixture'
    (app_fixture / 'perm/diagnostic/data').mkdir(parents=True)
    (app_fixture / '.ventuno-app-storage').write_text('ventuno-appdata-v1 ' + profile['filesystem_uuid'] + '\n')
    appfs = work / 'application.ext4'
    with appfs.open('wb') as f: f.truncate(128 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-U', profile['filesystem_uuid'], '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(app_fixture), str(appfs)], check=True)
    nvme = work / 'nvme.gpt'
    with nvme.open('wb') as f: f.truncate(130 * 1024 * 1024)
    layout = f"label: gpt\nlabel-id: {profile['disk_guid']}\n\nstart=2048, size=262144, type=linux, uuid={profile['partition_uuid']}\n"
    subprocess.run(['sfdisk', '--quiet', str(nvme)], input=layout, text=True, check=True)
    with appfs.open('rb') as src, nvme.open('r+b') as dst:
        dst.seek(1024 * 1024); shutil.copyfileobj(src, dst)
    store = output / 'pvstore.ext4'
    previous = None
    for name in ('update', 'commit-fail', 'recover'):
        case_logs = logs / name
        case_logs.mkdir()
        trial = uuid.uuid4().hex
        fixture = work / ('fixture-' + name)
        directory = fixture / 'boot/pantavisor-diagnostic' / trial
        directory.mkdir(parents=True)
        (directory / 'trial-id').write_text(trial + '\n')
        shutil.copyfile(store, directory / 'pvstore.ext4')
        (fixture / 'etc').mkdir()
        (fixture / 'etc/os-release').write_text('NAME="Local update fixture"\n')
        support = work / ('support-' + name + '.ext4')
        with support.open('wb') as f: f.truncate(512 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(fixture), str(support)], check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        deadline = 360 if name != 'recover' else 110
        boot_revision = '0' if name == 'update' else previous['last_good_revision']
        command = [
            'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57', '-m', '1024', '-smp', '2',
            '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot',
            '-kernel', str(output / ('vmlinuz-' + inputs['kernel_release'])), '-initrd', str(output / 'initramfs-ventuno-q.cpio.gz'),
            '-drive', f'file={support},format=raw,if=virtio', '-drive', f'file={nvme},format=raw,if=none,id=appdisk',
            '-device', f"nvme,drive=appdisk,serial={profile['serial']}",
            '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:2222', '-device', 'virtio-net-pci,netdev=net0',
            '-append', f'rdinit=/init console=ttyAMA0 panic=5 ventuno_trial={trial} ventuno_trace_device=/dev/vda ventuno_return_seconds={deadline} pv_rev={boot_revision}',
        ]
        after = case_logs / 'pvstore-after.ext4'
        with (case_logs / 'console.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                until = time.monotonic() + 75
                while time.monotonic() < until:
                    reply = subprocess.run(ssh_command('127.0.0.1', port), capture_output=True, text=True, timeout=10)
                    if reply.returncode == 0 and 'DHCP_BOUND=1' in reply.stdout: break
                    if process.poll() is not None: raise RuntimeError('Guest exited before SSH')
                    time.sleep(2)
                else: raise RuntimeError('SSH did not become available; inspect ' + str(case_logs))
                session = Session('127.0.0.1', port, case_logs)
                if name == 'update':
                    previous = session.exercise(inputs, output, trial)
                elif name == 'commit-fail':
                    session.fail_after_commit(inputs, previous)
                else:
                    session.wait_ready('rollback-recovered', inputs, previous['last_good_revision'], '2.0.0', previous['expected_after_rollback_boot'], previous['application_identity'], core_starts=3, require_done=True)
                    progress = json.loads(session.control('steps', 'show-progress', previous['failed_revision']))
                    assert progress['status'] == 'ERROR' and 'goal' in progress['status-msg'].lower(), progress
                    (case_logs / 'failed-progress.json').write_text(json.dumps(progress, indent=2) + '\n')
                    session.shells(inputs)
                assert process.wait(timeout=deadline + 30) == 0
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=10)
                subprocess.run(['debugfs', '-R', f'dump /boot/pantavisor-diagnostic/{trial}/pvstore.ext4 {after}', str(support)], check=True)
        text = (case_logs / 'console.log').read_text(errors='replace')
        assert 'Kernel panic' not in text and 'PID1_GUARDIAN_FALLBACK' not in text
        assert 'PANTAVISOR_NATIVE_SHUTDOWN_COMPLETE=1' in text
        trace = read(support, f'/boot/pantavisor-diagnostic/{trial}/trial.log')
        (case_logs / 'persistent-trace.log').write_text(trace)
        assert 'APPDATA_CLEANLY_UNMOUNTED=1' in trace and 'RUNTIME_CLEANUP_UNMOUNT_FAILURES=0' in trace
        fsck(support); fsck(after)
        if name != 'update':
            progress = json.loads(read(after, '/trails/locals/app-unready/.pv/progress'))
            assert progress['status'] == 'ERROR' and 'goal' in progress['status-msg'].lower(), progress
            assert 'pv_rev=' + previous['last_good_revision'] in read(after, '/boot/grubenv')
        with nvme.open('rb') as src, appfs.open('wb') as dst:
            src.seek(1024 * 1024)
            remaining = 128 * 1024 * 1024
            while remaining:
                chunk = src.read(min(1024 * 1024, remaining)); assert chunk
                dst.write(chunk); remaining -= len(chunk)
        fsck(appfs)
        assert read(appfs, '/perm/diagnostic/data/identity') == previous['application_identity']
        expected = previous['initial_starts'] + {'update': 3, 'commit-fail': 5, 'recover': 6}[name]
        assert read(appfs, '/perm/diagnostic/data/boots') == str(expected)
        store = after
        print(f'PASS: {name}, native shutdown, NVMe counter={expected}, filesystems clean', flush=True)
    shutil.copyfile(appfs, logs / 'application-after.ext4')
print('PASS: shells, local update/rollback, committed v2, automatic rejection and recovery of v2; evidence:', logs)
