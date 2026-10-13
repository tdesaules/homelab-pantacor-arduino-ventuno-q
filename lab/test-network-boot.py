#!/usr/bin/env python3
"""Test DHCP, pinned key-only SSH and automatic reboot in a full QEMU guest."""
import argparse
import json
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
import time
import uuid
from diagnostic_ssh import ROOT, ssh_command
from runtime_validation import is_ready, is_stopped, network_ready, core_ready, host_pid1_ready

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-ethernet-only')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs.get('network_profile')
runtime = inputs.get('embedded_runtime', False)
revision_network = inputs.get('revision_network', False)
component = inputs.get('management_container') or 'network'
def management_ready(text, starts):
    if component == 'core':
        return (core_ready(text, starts, inputs['core_image']['release'])
                and (not inputs.get('pid1_runtime') or host_pid1_ready(text)))
    return network_ready(text, starts)
status_command = 'ventuno-revision-status' if revision_network else 'ventuno-runtime-status'
trial = uuid.uuid4().hex
logs = output / 'qemu-network-test'
logs.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-network-') as temp:
    temp = Path(temp)
    fixture = temp / 'fixture'
    directory = fixture / 'boot/pantavisor-diagnostic' / trial
    directory.mkdir(parents=True)
    (directory / 'trial-id').write_text(trial + '\n')
    if runtime:
        shutil.copyfile(output / 'pvstore.ext4', directory / 'pvstore.ext4')
    (fixture / 'etc').mkdir()
    (fixture / 'etc/os-release').write_text('NAME="QEMU network fixture"\n')
    disk = temp / 'trace.ext4'
    with disk.open('wb') as stream:
        stream.truncate((512 if runtime else 128) * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-E', 'lazy_itable_init=0,lazy_journal_init=0',
                    '-d', str(fixture), str(disk)], check=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [
        'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
        '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot',
        '-kernel', str(output / ('vmlinuz-' + inputs['kernel_release'])),
        '-initrd', str(output / 'initramfs-ventuno-q.cpio.gz'),
        '-drive', f'file={disk},format=raw,if=virtio',
        '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:2222',
        '-device', 'virtio-net-pci,netdev=net0',
        '-append', f'rdinit=/init console=ttyAMA0 loglevel=7 panic=5 ventuno_trial={trial} '
                   f'ventuno_trace_device=/dev/vda ventuno_return_seconds={150 if runtime else 90}',
    ]
    with (logs / 'console.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            start = time.monotonic()
            last_error = 'No SSH response'
            while time.monotonic() - start < 65:
                try:
                    result = subprocess.run(ssh_command('127.0.0.1', port), capture_output=True, text=True, timeout=10)
                except subprocess.TimeoutExpired:
                    last_error = 'SSH command timed out'
                    continue
                last_error = result.stdout + result.stderr
                if result.returncode == 0:
                    assert 'ventuno_trial=' + trial in result.stdout
                    assert 'DHCP_BOUND=1' in result.stdout and '10.0.2.15' in result.stdout
                    (logs / 'ssh-success.log').write_text(result.stdout + result.stderr)
                    print('PASS: DHCP and authenticated SSH with pinned host key', flush=True)
                    break
                if process.poll() is not None:
                    raise RuntimeError('Guest exited before SSH became available')
                time.sleep(2)
            else:
                (logs / 'ssh-failure.log').write_text(last_error)
                raise RuntimeError('SSH validation failed: ' + last_error)
            wrong = temp / 'wrong-key'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(wrong)], check=True)
            denied = subprocess.run(ssh_command('127.0.0.1', port, identity=wrong, command='true'), capture_output=True, text=True, timeout=10)
            assert denied.returncode == 255 and 'Permission denied (publickey)' in denied.stderr
            (logs / 'ssh-rejected.log').write_text(denied.stderr)
            print('PASS: unauthorized key rejected; password authentication not offered', flush=True)
            if runtime:
                ready = False
                for _ in range(30):
                    state = subprocess.run(ssh_command('127.0.0.1', port, command=status_command), capture_output=True, text=True, timeout=10)
                    (logs / 'runtime-status.log').write_text(state.stdout + state.stderr)
                    if state.returncode == 0 and is_ready(state.stdout, 1) and (not revision_network or management_ready(state.stdout, 1)):
                        ready = True
                        break
                    if process.poll() is not None: break
                    time.sleep(2)
                assert ready, f'Runtime did not reach READY; inspect {logs}'
                print('PASS: revision 0 and LXC diagnostic container READY with persistent heartbeat', flush=True)
                if revision_network:
                    # The server lives in the container being restarted: this
                    # connection may close before the accepted request returns.
                    request = subprocess.run(ssh_command('127.0.0.1', port, command=status_command + ' restart ' + component), capture_output=True, text=True, timeout=10)
                    (logs / 'network-restart-request.log').write_text(request.stdout + request.stderr)
                    for _ in range(25):
                        time.sleep(1)
                        state = subprocess.run(ssh_command('127.0.0.1', port, command=status_command), capture_output=True, text=True, timeout=10)
                        (logs / 'network-restarted.log').write_text(state.stdout + state.stderr)
                        if state.returncode == 0 and is_ready(state.stdout, 1) and management_ready(state.stdout, 2):
                            break
                    else:
                        raise AssertionError('Revision network did not recover after restart')
                    print('PASS: revision-owned SSH/DHCP restarted; reconnect with pinned key; application uninterrupted', flush=True)
                subprocess.run(ssh_command('127.0.0.1', port, command=status_command + ' restart diagnostic'), capture_output=True, text=True, timeout=10, check=True)
                restarted = False
                for _ in range(15):
                    state = subprocess.run(ssh_command('127.0.0.1', port, command=status_command), capture_output=True, text=True, timeout=10)
                    (logs / 'runtime-restarted.log').write_text(state.stdout + state.stderr)
                    if state.returncode == 0 and is_ready(state.stdout, 2):
                        restarted = True; break
                    time.sleep(2)
                assert restarted, 'Container restart/persistence validation failed'
                subprocess.run(ssh_command('127.0.0.1', port, command=status_command + ' stop diagnostic'), capture_output=True, text=True, timeout=10, check=True)
                stopped = False
                for _ in range(10):
                    state = subprocess.run(ssh_command('127.0.0.1', port, command=status_command), capture_output=True, text=True, timeout=10)
                    (logs / 'runtime-stopped.log').write_text(state.stdout + state.stderr)
                    if state.returncode == 0 and is_stopped(state.stdout):
                        stopped = True; break
                    time.sleep(1)
                assert stopped, 'Stop request was accepted but the container did not stop'
                print('PASS: container restart retained data; container stopped before return', flush=True)
            assert process.wait(timeout=170 if runtime else 110) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            if runtime:
                subprocess.run(['debugfs', '-R', f'dump /boot/pantavisor-diagnostic/{trial}/pvstore.ext4 {logs / "pvstore-after.ext4"}', str(disk)], check=True)
    text = (logs / 'console.log').read_text(errors='replace')
    assert 'Kernel panic' not in text
    if inputs.get('pid1_runtime'):
        assert 'PANTAVISOR_PID1_HANDOFF' in text
        assert 'PANTAVISOR_CHILD_STARTED' not in text
        assert 'PANTAVISOR_NATIVE_SHUTDOWN_COMPLETE=1' in text
        assert 'PID1_GUARDIAN_FALLBACK' not in text
    else:
        assert 'RETURN_REQUESTED' in text
    diagnostic = subprocess.check_output(['debugfs', '-R', f'cat /boot/pantavisor-diagnostic/{trial}/trial.log', str(disk)], text=True)
    (logs / 'persistent-trace.log').write_text(diagnostic)
    assert 'DHCP_BOUND=1' in diagnostic
    assert 'TRIAL_DIAGNOSTICS_COMPLETE=' + trial in diagnostic
    if runtime:
        assert 'RUNTIME_CLEANUP_UNMOUNT_FAILURES=0' in diagnostic
        if inputs.get('pid1_runtime'):
            assert 'HOST_PID1_NAME=pantavisor' in diagnostic
            assert 'HOST_PID1_EXE=/usr/bin/pantavisor' in diagnostic
            assert 'PANTAVISOR_REBOOT_REQUESTED=1' in diagnostic
            assert 'PANTAVISOR_STORAGE_UNMOUNTED=1' in diagnostic
            print('PASS: Pantavisor is host PID 1; native orderly reboot without guardian fallback', flush=True)
        subprocess.run(['e2fsck', '-f', '-n', str(disk)], check=True)
        subprocess.run(['e2fsck', '-f', '-n', str(logs / 'pvstore-after.ext4')], check=True)
        boots = subprocess.check_output(['debugfs', '-R', 'cat /disks/perm/diagnostic/data/boots', str(logs / 'pvstore-after.ext4')], text=True).strip()
        assert boots == '2', boots
        if revision_network:
            assert ('NETWORK_OWNER=core' if component == 'core' else 'NETWORK_OWNER=revision') in diagnostic
            assert 'NETWORK_CHILD_STARTED' not in diagnostic
            boots = subprocess.check_output(['debugfs', '-R', f'cat /disks/perm/{component}/data/boots', str(logs / 'pvstore-after.ext4')], text=True).strip()
            assert boots == '2', boots
            if component == 'core':
                assert text.index("platform 'core' status is now READY") < text.index("starting platform 'diagnostic'")
                print('PASS: core READY before app startup; mgmt denied to application (HTTP 403); embedded core version verified', flush=True)
        print('PASS: store consistent after reboot; application counter persisted at 2', flush=True)
    print('PASS: persistent network trace and automatic reboot')
