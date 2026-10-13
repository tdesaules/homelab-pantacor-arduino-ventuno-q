#!/usr/bin/env python3
"""Check prototype hashes, cpio contents, ARM64 binaries and required vendor modules."""
import gzip
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import stat
import subprocess
import tempfile
import socket
import threading
from initramfs_archive import newc_members

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/prototype-1084')
parser.add_argument('--emulate', action='store_true', help='Execute only Pantavisor --version under qemu-aarch64')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
release = inputs['kernel_release']
for line in (output / 'SHA256SUMS').read_text().splitlines():
    expected, name = line.split('  ', 1)
    with (output / name).open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
print('PASS: artifact SHA-256 checksums')
entries = {name: (mode, data) for name, mode, data in newc_members(
    gzip.decompress((output / 'initramfs-ventuno-q.cpio.gz').read_bytes()))}

def resolve(name):
    name = name.lstrip('/')
    for _ in range(40):
        parts = name.split('/')
        for i in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:i])
            if prefix in entries and stat.S_ISLNK(entries[prefix][0]):
                target = entries[prefix][1].decode()
                target = target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(prefix), target)
                name = posixpath.normpath(posixpath.join(target, *parts[i:]))
                break
        else:
            assert name in entries, f'Missing path: {name}'
            return name
    raise ValueError(f'Symlink loop: {name}')

elfs = {}
executables = ['usr/bin/pantavisor', 'bin/busybox', 'sbin/modprobe']
if inputs.get('app_storage'):
    executables.append('sbin/blkid')
    assert inputs.get('pid1_runtime')
    config = entries['etc/ventuno-app-storage.conf'][1].decode()
    assert "APPDATA_UUID='" + inputs['app_storage']['filesystem_uuid'] + "'" in config
    helper = entries['usr/sbin/ventuno-app-storage'][1]
    assert helper == (root / 'meta-ventuno/recipes-core/ventuno-trial-guard/files/ventuno-app-storage').read_bytes()
    subprocess.run(['sh', '-n'], input=helper, check=True)
    assert b'mkfs' not in helper
    print('PASS: required UUID-based application storage helper; no runtime formatting')
if inputs.get('revision_network'):
    assert inputs.get('embedded_runtime')
    assert 'etc/ventuno-revision-network' in entries
    assert 'etc/ventuno-network.conf' not in entries
    assert 'home/root/.ssh/authorized_keys' not in entries
    assert 'etc/dropbear/dropbear_ed25519_host_key' not in entries
    print('PASS: revision owns networking; host has no network configuration or SSH credentials')
elif inputs.get('network_profile'):
    network = inputs['network_profile']
    executables.append('usr/sbin/dropbear')
    assert entries['home/root/.ssh/authorized_keys'][1].decode().strip() == network['client_public_key']
    assert entries['home/root/.ssh/authorized_keys'][0] & 0o777 == 0o600
    assert entries['etc/dropbear/dropbear_ed25519_host_key'][0] & 0o777 == 0o600
    assert 'home/root/.ssh/client_ed25519' not in entries
    assert ('ETHERNET_MAC=\'' + network['ethernet_mac'] + "'") in entries['etc/ventuno-network.conf'][1].decode()
    for image_path, source in (
        ('usr/sbin/ventuno-network', 'ventuno-network'),
        ('usr/lib/ventuno/udhcpc.script', 'udhcpc.script'),
    ):
        assert entries[image_path][1] == (root / 'meta-ventuno/recipes-core/ventuno-trial-guard/files' / source).read_bytes()
        subprocess.run(['sh', '-n'], input=entries[image_path][1], check=True)
    print('PASS: DHCP/SSH configuration and key permissions; client private key not installed')
if inputs.get('bounded_trial') or inputs.get('autonomous_boot'):
    assert inputs.get('trial_supervisor_version') == (5 if inputs.get('autonomous_boot') else 4 if inputs.get('pid1_runtime') else 2)
    assert entries['init'][1] == entries['usr/sbin/ventuno-return-guard'][1]
    assert entries['init'][0] & 0o111
    executables.append('init')
    executables.append('usr/sbin/ventuno-return-guard')
    if inputs.get('autonomous_boot'):
        executables.append('usr/sbin/ventuno-bootctl')
        assert 'etc/ventuno-autonomous' in entries
        assert inputs['trial_max_seconds'] == 0
    assert 'usr/sbin/ventuno-trial-diagnostics' in entries
    assert entries['usr/sbin/ventuno-trial-diagnostics'][1] == (root / 'meta-ventuno/recipes-core/ventuno-trial-guard/files/ventuno-trial-diagnostics').read_bytes()
    subprocess.run(['sh', '-n'], input=entries['usr/sbin/ventuno-trial-diagnostics'][1], check=True)
    supervised_config = entries['etc/ventuno-supervised.config'][1].decode().splitlines()
    for setting in ('PV_SYSTEM_INIT_MODE=standalone', 'PV_SYSTEM_DRIVERS_LOAD_EARLY_AUTO=0',
                    'PV_DEBUG_SHELL=0', 'PV_DEBUG_SSH=0'):
        assert setting in supervised_config, setting
    if inputs.get('embedded_runtime'):
        embedded = entries['etc/ventuno-embedded.config'][1].decode().splitlines()
        for setting in ('PV_SYSTEM_INIT_MODE=embedded', 'PV_STORAGE_DEVICE=/dev/loop32',
                        'PV_WDT_MODE=disabled', 'PV_CONTROL_REMOTE=0', 'PV_LOOP_INDEX_BASE=64'):
            assert setting in embedded, setting
        assert 'usr/share/ventuno/diagnostic.squashfs' in entries
        assert 'usr/sbin/ventuno-runtime' in entries
else:
    executables.append('init')
for path in executables:
    resolved = resolve(path)
    mode, data = entries[resolved]
    assert stat.S_ISREG(mode) and mode & 0o111, path
    assert data[:6] == b'\x7fELF\x02\x01' and int.from_bytes(data[18:20], 'little') == 183, path
    elfs[resolved] = data
    print(f'PASS: executable ARM64 {path} -> {resolved}')

config = entries['etc/pantavisor.config'][1].decode()
mode = 'embedded' if inputs.get('pid1_runtime') else 'standalone'
storage = '/dev/loop32' if inputs.get('pid1_runtime') else 'LABEL=pvstore'
for setting in (f'PV_SYSTEM_INIT_MODE={mode}', 'PV_BOOTLOADER_TYPE=grub', f'PV_STORAGE_DEVICE={storage}', 'PV_CONTROL_REMOTE=0'):
    assert setting in config.splitlines(), setting
if inputs.get('pid1_runtime'):
    assert entries['etc/pantavisor.config'][1] == entries['etc/ventuno-embedded.config'][1]
    assert 'etc/ventuno-pid1' in entries
    assert entries['usr/sbin/ventuno-pid1-shutdown'][1] == (root / 'meta-ventuno/recipes-core/ventuno-trial-guard/files/ventuno-pid1-shutdown').read_bytes()
    assert entries['usr/sbin/ventuno-storage-watch'][1] == (root / 'meta-ventuno/recipes-core/ventuno-trial-guard/files/ventuno-storage-watch').read_bytes()
    subprocess.run(['sh', '-n'], input=entries['usr/sbin/ventuno-storage-watch'][1], check=True)
print(f'PASS: {mode}/GRUB/local configuration')
if 'selection_policy' in inputs:
    enabled = '0' if inputs.get('pid1_runtime') else '1'
    for setting in (f'PV_SYSTEM_DRIVERS_LOAD_EARLY_AUTO={enabled}', f'PV_DEBUG_SHELL={enabled}', f'PV_DEBUG_SHELL_AUTOLOGIN={enabled}', 'PV_DEBUG_SSH=0'):
        assert setting in config.splitlines(), setting
    assert 'etc/mdev.conf' in entries
    assert 'usr/sbin/ventuno-load-drivers' in entries
    result = inputs['selection_result']
    for relative in result['modules']:
        resolve(f'lib/modules/{release}/{relative}')
    for relative in result['firmware']:
        resolve(f'lib/firmware/{relative}')
    for request in inputs['selection_policy']['firmware_required']:
        candidates = result['firmware_required'][request]
        assert candidates, request
        for candidate in candidates:
            resolve(f'lib/firmware/{candidate}')
    print(f'PASS: {len(result["modules"])} selected modules and {len(result["firmware"])} firmware files; early autoload and serial shell configured')

required_modules = ['nvme', 'dwmac-qcom-ethqos', 'overlay', 'xhci-pci']
wifi_enabled = inputs.get('selection_policy', {}).get('wifi_enabled', True)
if wifi_enabled:
    required_modules.append('ath11k_pci')
for module in required_modules:
    assert any(f'/modules/{release}/' in name and name.endswith('/' + module + '.ko.zst') for name in entries), module
assert any(name.endswith('/' + release + '/modules.dep.bin') for name in entries)
if wifi_enabled:
    assert any(name.endswith('/ath11k/WCN6855/hw2.1/amss.bin') for name in entries)
else:
    for forbidden in ('ath11k_pci', 'ath11k', 'mac80211', 'cfg80211'):
        assert not any(name.endswith(('/' + forbidden + '.ko.zst', '/' + forbidden + '.ko')) for name in entries), forbidden
    assert not any('/firmware/' in name and '/ath11k/' in name for name in entries)
    blocked = entries['etc/modprobe.d/90-ventuno-no-wifi.conf'][1].decode()
    assert 'blacklist ath11k_pci' in blocked and "install ath11k_pci /bin/sh -c 'exit 1'" in blocked
    resolve('bin/sh')
    print('PASS: Wi-Fi drivers/firmware excluded and onboard driver blocked')
print('PASS: required vendor modules and depmod indexes')

# Check loaders and transitive DT_NEEDED names against the archive inventory.
checked = set()
libraries = {}
with tempfile.TemporaryDirectory() as temp:
    while elfs:
        path, data = elfs.popitem()
        if path in checked:
            continue
        checked.add(path)
        binary = Path(temp) / 'elf'
        binary.write_bytes(data)
        details = subprocess.check_output(['readelf', '-l', '-d', str(binary)], text=True)
        if (inputs.get('bounded_trial') or inputs.get('autonomous_boot')) and path in ('init', 'usr/sbin/ventuno-return-guard'):
            assert 'INTERP' not in details and '(NEEDED)' not in details, 'Supervisor must be static'
        for interpreter in re.findall(r'Requesting program interpreter: ([^\]]+)', details):
            loader = resolve(interpreter)
            elfs[loader] = entries[loader][1]
        for soname in re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', details):
            candidate = next((p for p in ('lib/' + soname, 'usr/lib/' + soname) if p in entries), None)
            assert candidate, f'{path} needs missing {soname}'
            dependency = resolve(candidate)
            elfs[dependency] = entries[dependency][1]
            libraries[soname] = entries[dependency][1]
assert any('libzstd.so' in name for name in checked), 'kmod dependency chain lacks Zstd support'
print(f'PASS: dynamic loaders/dependencies present ({len(checked)} ELF files); Zstd linked')
if args.emulate:
    with tempfile.TemporaryDirectory(prefix='ventuno-qemu-') as temp:
        temp = Path(temp)
        for name, data in libraries.items():
            (temp / name).write_bytes(data)
        loader = temp / 'loader'
        loader.write_bytes(entries[resolve('lib/ld-musl-aarch64.so.1')][1])
        loader.chmod(0o755)
        executable = temp / 'pantavisor'
        executable.write_bytes(entries[resolve('usr/bin/pantavisor')][1])
        executable.chmod(0o755)
        result = subprocess.run(['qemu-aarch64', str(loader), '--library-path', str(temp),
                                 str(executable), '--version'], check=True,
                                capture_output=True, text=True, timeout=15)
        assert 'version:' in result.stdout
        print('PASS: QEMU ARM64 execution:', result.stdout.strip())
        (output / 'emulated-version.txt').write_text(result.stdout + result.stderr)
        busybox = temp / 'sh'
        busybox.write_bytes(entries[resolve('bin/busybox')][1])
        busybox.chmod(0o755)
        required = {'sh', 'mdev', 'ip', 'ls', 'cat', 'mount', 'umount', 'dd', 'reboot'}
        if inputs.get('bounded_trial') or inputs.get('autonomous_boot'):
            required |= {'mkdir', 'sleep', 'sync', 'date', 'uname', 'dmesg'}
        if inputs.get('network_profile'):
            required |= {'udhcpc', 'ifconfig', 'readlink', 'rm', 'mv', 'id'}
        if inputs.get('embedded_runtime'):
            required |= {'losetup', 'mknod', 'nsenter'}
        applets = {name.rsplit('/', 1)[-1] for name in entries
                   if name.startswith(('bin/', 'sbin/', 'usr/bin/', 'usr/sbin/'))}
        assert required <= applets, required - applets
        shell_output = subprocess.check_output([
            'qemu-aarch64', str(loader), '--library-path', str(temp), str(busybox),
            '-c', 'printf "ventuno-shell-ok\\n"',
        ], text=True, timeout=15)
        assert shell_output.strip() == 'ventuno-shell-ok'
        print('PASS: diagnostic commands present; BusyBox shell executes under QEMU')
        if inputs.get('bounded_trial') or inputs.get('autonomous_boot'):
            guard = temp / 'guard'
            guard.write_bytes(entries[resolve('usr/sbin/ventuno-return-guard')][1])
            guard.chmod(0o755)
            test = subprocess.check_output(['qemu-aarch64', str(guard), '--self-test'], text=True, timeout=15)
            if inputs.get('pid1_runtime'):
                assert 'supervisor-v4' in test and 'maximum=1800s' in test
                assert inputs['trial_max_seconds'] == (0 if inputs.get('autonomous_boot') else 1800)
            if inputs.get('autonomous_boot'): assert 'autonomous-v5' in test
            print(test.strip())
        if inputs.get('autonomous_boot'):
            control = temp / 'bootctl'
            control.write_bytes(entries[resolve('usr/sbin/ventuno-bootctl')][1])
            control.chmod(0o755)
            for state, expected in (('READY', 1), ('STARTING', 0)):
                path = str(temp / ('health-' + state))
                body = json.dumps([{'name': 'core', 'status': 'READY', 'status_goal': 'READY', 'user_stopped': 'false'},
                                   {'name': 'diagnostic', 'status': state, 'status_goal': 'READY', 'user_stopped': 'false'}]).encode()
                with socket.socket(socket.AF_UNIX) as server:
                    server.bind(path); server.listen(1); server.settimeout(10)
                    def respond():
                        connection, _ = server.accept()
                        with connection:
                            connection.recv(4096)
                            connection.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                    thread = threading.Thread(target=respond)
                    thread.start()
                    result = subprocess.check_output(['qemu-aarch64', str(loader), '--library-path', str(temp), str(control), 'health', path], text=True, timeout=10)
                    thread.join(timeout=10)
                    assert f'ready={expected}' in result.splitlines(), result
            print('PASS: ARM64 health client distinguishes actual READY from status_goal READY')
print('Hardware boot, containers and rollback remain untested.')
