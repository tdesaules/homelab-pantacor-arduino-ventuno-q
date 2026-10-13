"""Full isolated QEMU qualification using public bundles and ephemeral keys."""
import json
import socketserver
import struct
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from pathlib import Path
import shutil
from .build import verify_bundle
from .model import ROOT, canonical, digest, load


class NTPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        packet, socket = self.request
        if len(packet) < 48: return
        def stamp():
            value = time.time() + 2208988800
            return struct.pack('!II', int(value), int((value % 1) * 2**32))
        reply = bytearray(48)
        reply[:4] = bytes((0x24, 1, 4, 236))
        reply[12:16] = b'LOCL'
        reply[16:24] = stamp()
        reply[24:32] = packet[40:48]
        reply[32:40] = stamp()
        reply[40:48] = stamp()
        socket.sendto(reply, self.client_address)


def integration(base_directory, cluster_directory=None):
    base = verify_bundle(base_directory)
    cluster = verify_bundle(cluster_directory) if cluster_directory else None
    if base['profile'] != 'base' or cluster and cluster['profile'] != 'k0s': raise ValueError('Wrong integration bundles')
    if cluster and (cluster['source']['commit'], cluster['version']) != (base['source']['commit'], base['version']):
        raise ValueError('Integration inputs have different source identities')
    profile = 'k0s' if cluster else 'base'
    work = ROOT / 'artifacts/ci-integration' / (profile + '-' + uuid.uuid4().hex)
    work.mkdir(parents=True, mode=0o700)
    ssh = ROOT / 'artifacts/diagnostic-ssh'
    if ssh.exists(): raise ValueError('Refusing to overwrite existing lab SSH credentials; use a clean CI workspace')
    ssh.mkdir(mode=0o700)
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(ssh / 'client_ed25519')], check=True)
    subprocess.run(['dropbearkey', '-t', 'ed25519', '-f', str(ssh / 'dropbear_ed25519_host_key')],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    public = subprocess.check_output(['dropbearkey', '-y', '-f', str(ssh / 'dropbear_ed25519_host_key')], text=True)
    public = next(line for line in public.splitlines() if line.startswith('ssh-ed25519 '))
    (ssh / 'host_ed25519.pub').write_text(public + '\n')
    (ssh / 'known_hosts').write_text('ventuno-diagnostic ' + public + '\n')
    server = socketserver.ThreadingUDPServer(('127.0.0.1', 0), NTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        network = {'ethernet_mac': '02:00:00:00:00:01', 'ssh_port': 2222,
                   'client_public_key': (ssh / 'client_ed25519.pub').read_text().strip(),
                   'host_public_key': public, 'host_key_file': str(ssh / 'dropbear_ed25519_host_key'),
                   'ntp_servers': ['10.0.2.2:' + str(server.server_address[1])]}
        (work / 'network.json').write_bytes(canonical(network))
        nvme = {'schema': 1, 'name': 'nvme-apps', 'filesystem_uuid': str(uuid.uuid4()),
                'partition_uuid': str(uuid.uuid4()), 'disk_guid': str(uuid.uuid4()), 'serial': 'VENTUNO-CI'}
        (work / 'nvme.json').write_bytes(canonical(nvme))
        if cluster is None:
            # Qualify the current native base, including its independent rescue
            # and an actual serial-console command, with only ephemeral inputs.
            from .render import render
            from .native import prepare
            from .native_test import qualify
            system_uuid = str(uuid.uuid4())
            device = work / 'device.json'
            device.write_bytes(canonical({'schema': 1, 'rootUUID': system_uuid,
                'memoryKiB': 2 * 1024 * 1024, 'ethernetMAC': network['ethernet_mac'],
                'authorizedKeys': [network['client_public_key']],
                'sshHostKeyFile': network['host_key_file']}))
            override = work / 'native.json'
            override.write_bytes(canonical({'bootContract': 'emmc-file-store-v1',
                'containers': {'core': {'settings': {'ntpServers': network['ntp_servers']}}}}))
            state = work / 'native-state'
            render([base_directory], 'base', device, state, overrides=[override])
            package = work / 'native-package'
            prepare(state, system_uuid, Path('/usr/lib/grub/arm64-efi'), package,
                    emulated=True, size_mib=1024)
            qualify(package, ssh / 'client_ed25519', public, work / 'native-results')
            print('PASS: isolated native base integration')
            return
        bsp = base_directory / base['components']['bsp']['directory']
        output = work / 'prototype'
        subprocess.run([sys.executable, str(ROOT / 'lab/assemble-prototype.py'), str(bsp / 'initramfs-base.cpio.gz'),
            '--bsp', str(bsp / 'bsp.json'), '--vendor-archive', str(bsp / 'vendor-root.tar.gz'),
            '--selection', str(bsp / 'selection.json'), '--source-metadata', str(base_directory / 'bundle.json'),
            '--output-dir', str(output), '--autonomous', '--pid1', '--runtime', '--core', '--cgroup-v2',
            '--network-profile', str(work / 'network.json'), '--nvme-profile', str(work / 'nvme.json')], check=True)
        inputs = load(output / 'build-inputs.json')
        inputs['network_profile']['ntp_servers'] = network['ntp_servers']
        (output / 'build-inputs.json').write_bytes(canonical(inputs))
        deploy = ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q'
        deploy.mkdir(parents=True, exist_ok=False)
        selected, bundle = (cluster_directory, cluster) if cluster else (base_directory, base)
        core_name = 'core-kubernetes' if cluster else 'core'
        for component, prefix in [(core_name, 'ventuno-core-image')] + ([('k0s', 'ventuno-k0s-image')] if cluster else []):
            directory = selected / bundle['components'][component]['directory']
            shutil.copyfile(directory / 'rootfs.squashfs', deploy / (prefix + '-ventuno-q.squashfs'))
            shutil.copyfile(directory / 'packages.manifest', deploy / (prefix + '-ventuno-q.manifest'))
            if component == core_name:
                shutil.copyfile(directory / 'core-release.json', deploy / 'ventuno-core-image-ventuno-q.core-release.json')
        command = [sys.executable, str(ROOT / 'lab/build-first-revision.py'), '--output-dir', str(output), '--core-only']
        if cluster: command += ['--k0s', '--memory-kib', '3990200']
        subprocess.run(command, check=True)
        # Build GRUB locally from the runner's matching ARM64 modules. No binary
        # exported from the physical card is needed by this workflow.
        reference = ROOT / 'artifacts/grub-reference'
        reference.mkdir(exist_ok=False)
        root_uuid = str(uuid.uuid4())
        bootstrap = work / 'grub-bootstrap.cfg'
        bootstrap.write_text(f'search --no-floppy --fs-uuid --set=root {root_uuid}\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n')
        maker = shutil.which('grub-mkstandalone') or shutil.which('grub2-mkstandalone')
        subprocess.run([maker, '-O', 'arm64-efi', '--locales=', '--fonts=', '--themes=',
                        '-o', str(reference / 'grubaa64.efi'), 'boot/grub/grub.cfg=' + str(bootstrap)], check=True)
        modules = Path('/usr/lib/grub/arm64-efi')
        if not modules.is_dir(): raise RuntimeError('Install grub-efi-arm64-bin on the ARM64 runner')
        with tarfile.open(reference / 'arm64-efi.tar.gz', 'w:gz') as archive:
            archive.add(modules, arcname='arm64-efi')
        (reference / 'reference.json').write_bytes(canonical({'root_uuid': root_uuid,
            'sha256': digest(reference / 'grubaa64.efi'), 'modules_sha256': digest(reference / 'arm64-efi.tar.gz')}))
        subprocess.run([sys.executable, str(ROOT / 'lab/test-autonomous-boot.py'), '--output-dir', str(output),
                        '--default-boot', '--unsynced-clock'], check=True, timeout=2400)
        print('PASS: isolated full integration for', profile)
    finally:
        server.shutdown(); server.server_close()
