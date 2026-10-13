#!/usr/bin/env python3
"""Boot the board's real ARM64 GRUB through UEFI and chain reboots on one durable store."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
from autonomous_boot import ENTRY_ID, grub_default, grub_entry, grubenv
from diagnostic_ssh import ROOT
from persistent_session import exercise_autonomous
from core_only_session import exercise_core_only
import sys
sys.path.insert(0, str(ROOT))
from tools.pvbuild.host import grub_checker, efi_firmware, sparse_copy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-autonomous')
parser.add_argument('--default-boot', action='store_true')
parser.add_argument('--missing-nvme', action='store_true')
parser.add_argument('--failed-core', action='store_true')
parser.add_argument('--keep-on-failure', action='store_true', help='Keep the QEMU fixture alive for diagnosis after a failed assertion')
parser.add_argument('--unsynced-clock', action='store_true', help='Boot the VM at epoch zero to validate NTP before PKI creation')
faults = parser.add_mutually_exclusive_group()
faults.add_argument('--exhausted-budget', action='store_true', help='Verify GRUB returns to recovery before starting a fourth rapid boot')
faults.add_argument('--stalled-bootstrap', action='store_true', help='Verify the autonomous startup health deadline returns to recovery')
faults.add_argument('--budget-write-failure', action='store_true')
faults.add_argument('--core-only-bundle', type=Path, help='Qualify a core-only revision and retained NVMe data')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs['autonomous_boot'] and inputs['runtime_storage']['size'] == 1024 ** 3
reference = ROOT / 'artifacts/grub-reference'
grub = json.loads((reference / 'reference.json').read_text())
assert hashlib.sha256((reference / 'grubaa64.efi').read_bytes()).hexdigest() == grub['sha256']
assert hashlib.sha256((reference / 'arm64-efi.tar.gz').read_bytes()).hexdigest() == grub['modules_sha256']
profile = inputs['app_storage']
install_id = uuid.uuid4().hex
logs = output / 'qemu-autonomous-test' / install_id
logs.mkdir(parents=True)

def read(image, path): return subprocess.check_output(['debugfs', '-R', 'cat ' + path, str(image)], stderr=subprocess.DEVNULL, text=True).strip()
def fsck(image):
    # e2fsck -n can return zero despite skipped journal recovery; inspect flags too.
    header = subprocess.check_output(['dumpe2fs', '-h', str(image)], stderr=subprocess.DEVNULL, text=True)
    assert 'needs_recovery' not in header and 'orphan_present' not in header, header
    subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)

with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='qemu-autonomous-') as work:
    work = Path(work)
    fixture = work / 'fixture'
    directory = fixture / 'boot/pantavisor'
    (directory / 'state').mkdir(parents=True)
    (directory / 'logs').mkdir()
    for target, source in (('kernel', output / ('vmlinuz-' + inputs['kernel_release'])),
                           ('initramfs', output / 'initramfs-ventuno-q.cpio.gz'), ('pvstore.ext4', output / 'pvstore.ext4')):
        shutil.copyfile(source, directory / target)
    (directory / 'install-id').write_text(install_id + '\n')
    shutil.copyfile(output / 'boot-state.grubenv', directory / 'state/grubenv')
    (directory / 'state/boot-budget').write_bytes(grubenv({'ventuno_boots': '3' if args.exhausted_budget else '0'}))
    (fixture / 'boot/grub').mkdir()
    with tarfile.open(reference / 'arm64-efi.tar.gz') as archive: archive.extractall(fixture / 'boot/grub', filter='data')
    (fixture / 'boot/grub/grubenv').write_bytes(grubenv({} if args.default_boot else {'next_entry': ENTRY_ID}))
    config = '''set timeout=0
set default=0
load_env
if [ -n "$next_entry" ]; then
    set default="$next_entry"
    set boot_once=true
    set next_entry=
    save_env next_entry
fi
''' + (grub_default(grub['root_uuid']) if args.default_boot else '') + '''menuentry 'Ubuntu recovery fixture' --id ubuntu {
    echo 'UBUNTU_RECOVERY_SELECTED'
    halt
}
''' + grub_entry(grub['root_uuid'], install_id, emulated=True, stall_bootstrap=args.stalled_bootstrap, fail_budget_write=args.budget_write_failure)
    (fixture / 'boot/grub/grub.cfg').write_text(config)
    subprocess.run([grub_checker(), str(fixture / 'boot/grub/grub.cfg')], check=True)
    (fixture / 'etc').mkdir()
    (fixture / 'etc/os-release').write_text('NAME="Autonomous boot fixture"\n')
    support = work / 'support.ext4'
    with support.open('wb') as stream: stream.truncate(3 * 1024 ** 3)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-U', grub['root_uuid'], '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(fixture), str(support)], check=True)
    efi = work / 'efi'
    for folder in ('EFI/BOOT', 'EFI/ubuntu'):
        (efi / folder).mkdir(parents=True)
        (efi / folder / 'grub.cfg').write_text(f"search --no-floppy --fs-uuid --set=root {grub['root_uuid']}\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n")
    shutil.copyfile(reference / 'grubaa64.efi', efi / 'EFI/BOOT/BOOTAA64.EFI')
    app_fixture = work / 'app-fixture'
    (app_fixture / ('perm' if inputs.get('core_only') else 'perm/diagnostic/data')).mkdir(parents=True)
    if inputs.get('k0s'):
        for name in ('data', 'workloads', 'access', 'log'):
            (app_fixture / 'perm/k0s' / name).mkdir(parents=True)
    (app_fixture / '.ventuno-app-storage').write_text('ventuno-appdata-v1 ' + profile['filesystem_uuid'] + '\n')
    appfs = work / 'application.ext4'
    app_size = (4096 if inputs.get('k0s') else 128) * 1024 * 1024
    with appfs.open('wb') as stream: stream.truncate(app_size)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-U', profile['filesystem_uuid'], '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(app_fixture), str(appfs)], check=True)
    nvme = work / 'nvme.gpt'
    with nvme.open('wb') as stream: stream.truncate(app_size + 2 * 1024 * 1024)
    layout = f"label: gpt\nlabel-id: {profile['disk_guid']}\n\nstart=2048, size={app_size // 512}, type=linux, uuid={profile['partition_uuid']}\n"
    subprocess.run(['sfdisk', '--quiet', str(nvme)], input=layout, text=True, check=True)
    with appfs.open('rb') as source, nvme.open('r+b') as target:
        target.seek(1024 * 1024); sparse_copy(source, target, app_size)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); api_port = sock.getsockname()[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); web_port = sock.getsockname()[1]
    command = [
        'qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57', '-m', '4096' if inputs.get('k0s') else '2048', '-smp', '4' if inputs.get('k0s') else '2',
        '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-bios', efi_firmware(),
        '-drive', f'file={support},format=raw,if=virtio',
        '-drive', f'file=fat:ro:{efi},format=raw,if=virtio,readonly=on',
        '-drive', f'file={nvme},format=raw,if=none,id=appdisk', '-device', f"nvme,drive=appdisk,serial={profile['serial']}",
        '-netdev', f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:2222,hostfwd=tcp:127.0.0.1:{api_port}-:6443,hostfwd=tcp:127.0.0.1:{web_port}-:30080', '-device', 'virtio-net-pci,netdev=net0',
    ]
    if args.missing_nvme:
        index = command.index('-drive', command.index('-drive', command.index('-drive') + 1) + 1)
        del command[index:index + 4]
    if args.unsynced_clock:
        command += ['-rtc', 'base=1970-01-01T00:00:00']
    after = logs / 'pvstore-after.ext4'
    with (logs / 'console.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        (logs / 'connection.json').write_text(json.dumps({'ssh_port': port, 'api_port': api_port, 'web_port': web_port, 'qemu_pid': process.pid}, indent=2) + '\n')
        try:
            if not (args.exhausted_budget or args.stalled_bootstrap or args.budget_write_failure):
                if inputs.get('k0s'):
                    from k0s_session import exercise_k0s
                    result = exercise_k0s('127.0.0.1', port, api_port, web_port, logs, inputs, install_id, is_alive=lambda: process.poll() is None,
                                          pressure_test=bool(inputs.get('resource_policy')))
                elif inputs.get('core_only'):
                    from recovery_session import exercise_recovery
                    result = exercise_recovery('127.0.0.1', port, logs, inputs, install_id, is_alive=lambda: process.poll() is None, failed_core=args.failed_core)
                elif args.core_only_bundle:
                    result = exercise_core_only('127.0.0.1', port, logs, inputs, args.core_only_bundle, install_id, is_alive=lambda: process.poll() is None)
                else:
                    result = exercise_autonomous('127.0.0.1', port, logs, inputs, output, install_id, is_alive=lambda: process.poll() is None)
            assert process.wait(timeout=300 if args.stalled_bootstrap or args.failed_core else 120) == 0
            if args.default_boot:
                with (logs / 'recovery-cold-boot.log').open('wb') as recovery_log:
                    subprocess.run(command, stdout=recovery_log, stderr=subprocess.STDOUT, check=True, timeout=60)
                cold = (logs / 'recovery-cold-boot.log').read_text(errors='replace')
                assert 'UBUNTU_RECOVERY_SELECTED' in cold and 'AUTONOMOUS_TOKEN_VALID' not in cold
        except BaseException as error:
            if inputs.get('k0s') and process.poll() is None:
                from local_updates import Session
                try:
                    text = Session('127.0.0.1', port, logs).run('cat /k0s-access/status; cat /k0s-access/sysinfo.log; cat /k0s-access/service.log', timeout=30)
                    (logs / 'k0s-failed.log').write_text(text)
                except (RuntimeError, subprocess.TimeoutExpired): pass
            if args.keep_on_failure and not isinstance(error, KeyboardInterrupt):
                print('FAILED:', repr(error), '; QEMU retained for diagnosis:', logs, flush=True)
                while process.poll() is None: time.sleep(5)
            raise
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
            subprocess.run(['debugfs', '-R', f'dump /boot/pantavisor/pvstore.ext4 {after}', str(support)], check=True)
    console = (logs / 'console.log').read_text(errors='replace')
    assert 'UBUNTU_RECOVERY_SELECTED' in console
    if args.exhausted_budget or args.stalled_bootstrap or args.budget_write_failure:
        if args.exhausted_budget:
            assert 'PANTAVISOR_BOOT_BUDGET_EXHAUSTED' in console and 'AUTONOMOUS_TOKEN_VALID' not in console
        elif args.budget_write_failure:
            assert 'PANTAVISOR_BOOT_BUDGET_WRITE_FAILED' in console and 'AUTONOMOUS_TOKEN_VALID' not in console
        else:
            assert 'PID1_BOOTSTRAP_STALLED' in console and 'AUTONOMOUS_HEALTH_FAILURE' in console
            assert 'Kernel panic' not in console
        with after.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == inputs['runtime_storage']['sha256']
        fsck(support); fsck(after)
        print('PASS: autonomous fault returned to recovery with the original store intact; logs:', logs)
        raise SystemExit(0)
    if not args.core_only_bundle and not inputs.get('core_only') and not inputs.get('k0s'): assert console.count('PANTAVISOR_SELECTED=locals/app-unready') == 1
    assert ('AUTONOMOUS_HEALTH_FAILURE' in console) == args.failed_core
    assert 'Kernel panic' not in console
    fsck(support); fsck(after)
    env = read(support, '/boot/pantavisor/state/grubenv')
    main_env = read(support, '/boot/grub/grubenv')
    assert 'pv_rev=' + result.get('revision', 'locals/app-v2') in env
    assert 'next_entry=pantavisor-persistent' not in main_env
    (logs / 'private-grubenv.txt').write_text(env + '\n')
    assert read(after, '/disks/perm/core/data/boots') == str(result.get('core_starts', 4))
    with nvme.open('rb') as source, (logs / 'application-after.ext4').open('wb') as target:
        source.seek(1024 * 1024)
        sparse_copy(source, target, app_size)
        target.truncate(app_size)
    fsck(logs / 'application-after.ext4')
    if not inputs.get('core_only') and not inputs.get('k0s'):
        assert read(logs / 'application-after.ext4', '/perm/diagnostic/data/identity') == result['application_identity']
    else:
        assert ('APPDATA_MOUNTED=0' if args.missing_nvme else 'APPDATA_MOUNTED=1') in result['app_storage']
    if args.core_only_bundle:
        for name, expected in result['retained_data'].items():
            assert read(logs / 'application-after.ext4', '/perm/diagnostic/data/' + name) == expected
        state = json.loads(read(after, '/trails/locals/core-only-040/.pvr/json'))
        assert not any(key.startswith('diagnostic/') for key in state)
        print('PASS: retired application data unchanged on NVMe', flush=True)
    print('PASS: real UEFI/GRUB, one durable store, autonomous try-boot/rollback, explicit recovery and clean filesystems; logs:', logs)
