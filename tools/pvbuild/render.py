"""Render a private Pantavisor state from public release components and device inputs."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from .build import verify_bundle
from .model import ROOT, canonical, compose, digest, load, version


def validate_device(device, composition):
    if device.get('schema') != 1: raise ValueError('Unsupported device schema')
    uuid.UUID(device['rootUUID'])
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', device['ethernetMAC']): raise ValueError('Invalid Ethernet MAC')
    if type(device['memoryKiB']) is not int or device['memoryKiB'] < 1024 * 1024: raise ValueError('Invalid usable memory')
    if not device['authorizedKeys']: raise ValueError('At least one SSH public key is required')
    for key in device['authorizedKeys']:
        if '\n' in key or '\r' in key: raise ValueError('SSH keys must be single lines')
        fields = key.split()
        if len(fields) < 2 or fields[0] not in ('ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256'):
            raise ValueError('Expected an SSH public key, not a private credential')
        base64.b64decode(fields[1], validate=True)
    storage = device.get('appStorage')
    if 'k0s' in composition['containers'] and not storage: raise ValueError('The k0s layer requires NVMe configuration')
    if storage:
        uuid.UUID(storage['uuid']); uuid.UUID(storage['partuuid'])
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', storage['serial']): raise ValueError('Invalid NVMe serial')


def core_config(memory_mib, cpu_weight, cluster):
    config = f'''lxc.uts.name = ventuno-core
lxc.init.cmd = /usr/sbin/init.lxc.static --name core -- /usr/libexec/ventuno/core-init
lxc.signal.halt = SIGTERM
lxc.rootfs.path = overlay:/volumes/core/root.squashfs:/volumes/core/lxc-overlay/upper
lxc.mount.auto = proc:mixed sys:ro cgroup:ro:force
lxc.autodev = 1
lxc.tty.max = 0
lxc.pty.max = 16
lxc.console.path = none
lxc.apparmor.profile = unconfined
lxc.net.0.type = none
lxc.cap.drop = sys_module sys_rawio sys_boot
lxc.cgroup2.memory.max = {memory_mib * 1024**2}
lxc.cgroup2.cpu.weight = {cpu_weight}
lxc.mount.entry = /volumes/core/data data none bind,create=dir 0 0
lxc.mount.entry = /ventuno-trial trial-status none bind,ro,create=dir 0 0
lxc.mount.entry = /ventuno-trial/control boot-control none bind,create=dir 0 0
'''
    if cluster: config += 'lxc.mount.entry = /mnt/appdata/perm/k0s/access k0s-access none bind,ro,optional,create=dir 0 0\n'
    return config.encode()


def render(bundles, profile, device_path, output, *, overrides=(), layers=()):
    composition = compose(profile, overrides=overrides, layers=layers)
    device = load(device_path)
    validate_device(device, composition)
    components = {}
    checked = []
    for directory in bundles:
        bundle = verify_bundle(directory)
        checked.append((directory, bundle))
        for name, item in bundle['components'].items():
            if name in components: raise ValueError('Duplicate component: ' + name)
            components[name] = directory / item['directory']
    if len(checked) == 1 and checked[0][1].get('upstreamCompositionDigest'):
        if overrides or layers: raise ValueError('Compose a new lock before overriding a fetched release')
        composition = checked[0][1]['composition']
        validate_device(device, composition)
    versions = {bundle['version'] for _, bundle in checked}
    if len(versions) != 1: raise ValueError('Component release versions differ')
    release_version, = versions
    revision = 'locals/' + version(release_version)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / 'objects').mkdir(mode=0o700)
    core = composition['containers']['core']
    core_dir = components[core['artifact']]
    bsp_dir = components[composition['bsp']]
    bsp_metadata = load(bsp_dir / 'bsp.json')
    if composition['bootContract'] not in bsp_metadata.get('bootContracts', [bsp_metadata['bootContract']]):
        raise ValueError('BSP does not support the selected boot contract; rebuild it first')
    with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='device-key-') as temporary:
        unpacked = Path(temporary) / 'root'
        subprocess.run(['unsquashfs', '-no-progress', '-d', str(unpacked), str(core_dir / 'rootfs.squashfs')],
                       stdout=subprocess.DEVNULL, check=True)
        key = output / 'ssh-host-key'
        if device.get('sshHostKeyFile'):
            shutil.copyfile(device['sshHostKeyFile'], key)
        else:
            subprocess.run(['qemu-aarch64', '-L', str(unpacked), str(unpacked / 'usr/sbin/dropbearkey'), '-t', 'ed25519', '-f', str(key)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        key.chmod(0o600)
        public = subprocess.check_output(['qemu-aarch64', '-L', str(unpacked), str(unpacked / 'usr/sbin/dropbearkey'), '-y', '-f', str(key)], text=True)
        public = next(line for line in public.splitlines() if line.startswith('ssh-ed25519 '))
    network = {'ethernet_mac': device['ethernetMAC'], 'ssh_port': core['settings']['sshPort'],
               'client_public_key': device['authorizedKeys'][0], 'host_public_key': public, 'host_key_file': str(key.resolve())}
    # The validated lab bootstrap still expects port 2222. Other SSH ports are
    # supported in the rendered core configuration, not in that diagnostic flag.
    network['ssh_port'] = 2222
    network_path = output / 'network-profile.json'
    network_path.write_bytes(canonical(network))
    command = [sys.executable, str(ROOT / 'lab/assemble-prototype.py'), str(bsp_dir / 'initramfs-base.cpio.gz'),
        '--bsp', str(bsp_dir / 'bsp.json'), '--vendor-archive', str(bsp_dir / 'vendor-root.tar.gz'),
        '--selection', str(bsp_dir / 'selection.json'), '--source-metadata', str(checked[0][0] / 'bundle.json'),
        '--output-dir', str(output / 'bootstrap'), '--autonomous', '--pid1', '--runtime', '--core', '--cgroup-v2',
        '--network-profile', str(network_path)]
    if composition['bootContract'] == 'emmc-file-store-v1':
        command.append('--native')
    if device.get('appStorage'):
        storage = device['appStorage']
        nvme = {'schema': 1, 'name': 'nvme-apps', 'filesystem_uuid': storage['uuid'],
                'partition_uuid': storage['partuuid'], 'serial': storage['serial']}
        path = output / 'nvme-profile.json'
        path.write_bytes(canonical(nvme))
        command += ['--nvme-profile', str(path)]
    subprocess.run(command, check=True)
    bsp = load(bsp_dir / 'bsp.json')
    state = {'#spec': 'pantavisor-service-system@1',
             'bsp/run.json': {'linux': 'kernel.img', 'initrd': 'pantavisor'},
             'device.json': {'groups': [{'name': 'root', 'status_goal': 'READY', 'restart_policy': 'container', 'timeout': 45}]},
             'core/run.json': {'#spec': 'service-manifest-run@1', 'name': 'core', 'type': 'lxc', 'group': 'root',
                'config': 'lxc.container.conf', 'root-volume': 'root.squashfs', 'volumes': [], 'roles': ['mgmt'],
                'status_goal': 'READY', 'restart_policy': 'container',
                'storage': {'lxc-overlay': {'persistence': 'boot'}, 'data': {'persistence': 'permanent'}}}}
    def put(name, data):
        sha = hashlib.sha256(data).hexdigest()
        target = output / 'objects' / sha
        target.write_bytes(data); target.chmod(0o600)
        state[name] = sha
    put('bsp/kernel.img', (bsp_dir / 'kernel.img').read_bytes())
    put('bsp/pantavisor', (output / 'bootstrap/initramfs-ventuno-q.cpio.gz').read_bytes())
    put('core/root.squashfs', (core_dir / 'rootfs.squashfs').read_bytes())
    config = core_config(core['memoryMiB'], core['cpuWeight'], 'k0s' in composition['containers'])
    if composition['bootContract'] == 'emmc-file-store-v1':
        config += b'lxc.mount.entry = /mnt/pv-system/boot/pantavisor/state boot-state none bind,ro,create=dir 0 0\n'
    put('core/lxc.container.conf', config)
    put('_config/core/home/root/.ssh/authorized_keys', ('\n'.join(device['authorizedKeys']) + '\n').encode())
    put('_config/core/etc/dropbear/dropbear_ed25519_host_key', key.read_bytes())
    put('_config/core/etc/ventuno-network.conf', f"ETHERNET_MAC='{device['ethernetMAC']}'\nSSH_PORT={core['settings']['sshPort']}\n".encode())
    put('_config/core/etc/ventuno-time.conf', ('NTP_SERVERS=' + shlex.quote(' '.join(core['settings']['ntpServers'])) + '\n').encode())
    if 'k0s' in composition['containers']:
        # Reuse the qualified LXC adapter; the public composition then overrides
        # its parameterized limits and runtime settings explicitly.
        sys.path.insert(0, str(ROOT / 'lab'))
        from k0s_revision import add_k0s
        cluster = composition['containers']['k0s']
        state, objects = add_k0s(state, (output / 'objects' / state['core/lxc.container.conf']).read_bytes(),
                                (components[cluster['artifact']] / 'rootfs.squashfs').read_bytes(), bsp['kernel_release'],
                                core['memoryMiB'] * 1024**2, device['memoryKiB'])
        config = objects[state['k0s/lxc.container.conf']]
        limit = (device['memoryKiB'] // 1024 - cluster['hostReserveMiB']) * 1024**2
        if limit <= (cluster['kubeReserveMiB'] + cluster['evictionMiB']) * 1024**2:
            raise ValueError('Insufficient device memory for selected reservations')
        config = re.sub(rb'(?m)^lxc.cgroup2.memory.max = \d+$', f'lxc.cgroup2.memory.max = {limit}'.encode(), config)
        config = re.sub(rb'(?m)^lxc.cgroup2.memory.high = \d+$', f'lxc.cgroup2.memory.high = {limit - 256 * 1024**2}'.encode(), config)
        for sha, data in objects.items():
            target = output / 'objects' / sha
            target.write_bytes(data); target.chmod(0o600)
        put('k0s/lxc.container.conf', config)
        settings = cluster['settings']
        values = {'K0S_HOST_RESERVE_MIB': cluster['hostReserveMiB'], 'K0S_KUBE_RESERVE_MIB': cluster['kubeReserveMiB'],
                  'K0S_EVICTION_MIB': cluster['evictionMiB'], 'K0S_MAX_PODS': settings['maxPods'],
                  'K0S_POD_CIDR': settings['podCIDR'], 'K0S_SERVICE_CIDR': settings['serviceCIDR'],
                  'K0S_DISABLED_COMPONENTS': ','.join(settings['disabledComponents'])}
        put('_config/k0s/etc/ventuno/k0s.env', ''.join(f'{key}={shlex.quote(str(value))}\n' for key, value in values.items()).encode())
    (output / 'state.json').write_bytes(canonical(state))
    (output / 'device-state.json').write_bytes(canonical({'schema': 1, 'kind': 'private-device-state',
        'version': release_version, 'revision': revision, 'composition': composition,
        'stateSha256': digest(output / 'state.json'), 'sshHostPublicKey': public,
        'bootContract': composition['bootContract'], 'installationRequired': True}))
    return revision
