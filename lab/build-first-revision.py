#!/usr/bin/env python3
"""Seed a private 256 MiB ext4 image with revision 0, diagnostic and optional core."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from initramfs_archive import newc_members

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-runtime')
parser.add_argument('--replace-seed', action='store_true', help='Replace only a pristine local seed matching its recorded hash')
parser.add_argument('--store-size-mib', type=int, choices=(256, 1024))
parser.add_argument('--core-only', action='store_true', help='Seed only the management container')
parser.add_argument('--k0s', action='store_true', help='Seed the k0s POC alongside core')
parser.add_argument('--memory-kib', type=int, help='Usable memory of the target device for its k0s limit')
args = parser.parse_args()
output = args.output_dir.resolve()
inputs = json.loads((output / 'build-inputs.json').read_text())
assert inputs['embedded_runtime'] and (inputs['bounded_trial'] or inputs.get('autonomous_boot'))
autonomous = inputs.get('autonomous_boot', False)
size_mib = args.store_size_mib or (1024 if autonomous else 256)
assert not autonomous or size_mib == 1024
entries = {n: data for n, mode, data in newc_members(gzip.decompress((output / 'initramfs-ventuno-q.cpio.gz').read_bytes()))}
container = b'' if args.core_only else entries['usr/share/ventuno/diagnostic.squashfs']
lxc = '''lxc.uts.name = ventuno-diagnostic
lxc.init.cmd = /diagnostic
lxc.signal.halt = SIGTERM
lxc.rootfs.path = overlay:/volumes/diagnostic/root.squashfs:/volumes/diagnostic/lxc-overlay/upper
lxc.mount.auto = proc:mixed sys:ro cgroup:ro
lxc.autodev = 1
lxc.tty.max = 0
lxc.console.path = none
lxc.apparmor.profile = unconfined
lxc.net.0.type = empty
lxc.cap.drop = sys_module sys_rawio sys_boot
lxc.mount.entry = /volumes/diagnostic/data data none bind,create=dir 0 0
lxc.cgroup.memory.limit_in_bytes = 67108864
'''.encode()
state = {
    '#spec': 'pantavisor-service-system@1',
    'bsp/run.json': {'linux': 'kernel.img', 'initrd': 'pantavisor'},
    'device.json': {'groups': [{'name': 'app', 'status_goal': 'READY', 'restart_policy': 'container', 'timeout': 45}]},
    'diagnostic/run.json': {
        '#spec': 'service-manifest-run@1', 'name': 'diagnostic', 'type': 'lxc',
        'config': 'lxc.container.conf', 'root-volume': 'root.squashfs', 'volumes': [],
        'group': 'app', 'status_goal': 'READY', 'restart_policy': 'container',
        'roles': ['nobody'],
        'storage': {'lxc-overlay': {'persistence': 'boot'}, 'data': {'persistence': 'permanent'}},
    },
}
artifacts = {
    'bsp/kernel.img': (output / ('vmlinuz-' + inputs['kernel_release'])).read_bytes(),
    'bsp/pantavisor': (output / 'initramfs-ventuno-q.cpio.gz').read_bytes(),
    'diagnostic/root.squashfs': container, 'diagnostic/lxc.container.conf': lxc,
}
if inputs.get('revision_network'):
    assert inputs.get('management_container') == 'core', 'Reassemble with --core before building the new seed'
    deploy = ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q'
    core_image = deploy / 'ventuno-core-image-ventuno-q.squashfs'
    release = json.loads((deploy / 'ventuno-core-image-ventuno-q.core-release.json').read_text())
    assert release['name'] == 'ventuno-core'
    profile = inputs['network_profile']
    state['device.json']['groups'].insert(0, {
        'name': 'root', 'status_goal': 'READY', 'restart_policy': 'container', 'timeout': 45,
    })
    state['core/run.json'] = {
        '#spec': 'service-manifest-run@1', 'name': 'core', 'type': 'lxc',
        'config': 'lxc.container.conf', 'root-volume': 'root.squashfs', 'volumes': [],
        'group': 'root', 'status_goal': 'READY', 'restart_policy': 'container',
        'roles': ['mgmt'],
        'storage': {'lxc-overlay': {'persistence': 'boot'}, 'data': {'persistence': 'permanent'}},
    }
    core_lxc = '''lxc.uts.name = ventuno-core
lxc.init.cmd = /usr/sbin/init.lxc.static --name core -- /usr/libexec/ventuno/core-init
lxc.signal.halt = SIGTERM
lxc.rootfs.path = overlay:/volumes/core/root.squashfs:/volumes/core/lxc-overlay/upper
lxc.mount.auto = proc:mixed sys:ro cgroup:ro
lxc.autodev = 1
lxc.tty.max = 0
lxc.pty.max = 16
lxc.console.path = none
lxc.apparmor.profile = unconfined
lxc.net.0.type = none
lxc.cap.drop = sys_module sys_rawio sys_boot
lxc.cgroup.memory.limit_in_bytes = 536870912
lxc.mount.entry = /volumes/core/data data none bind,create=dir 0 0
lxc.mount.entry = /storage/disks/perm/diagnostic/data diagnostic-data none bind,ro,create=dir 0 0
'''
    artifacts.update({
        'core/root.squashfs': core_image.read_bytes(),
        'core/lxc.container.conf': core_lxc.encode(),
        '_config/core/home/root/.ssh/authorized_keys': (profile['client_public_key'] + '\n').encode(),
        '_config/core/etc/dropbear/dropbear_ed25519_host_key': (output / 'network-host-key').read_bytes(),
        '_config/core/etc/ventuno-network.conf': f"ETHERNET_MAC='{profile['ethernet_mac']}'\nSSH_PORT=2222\n".encode(),
    })
    if profile.get('ntp_servers'):
        import shlex
        artifacts['_config/core/etc/ventuno-time.conf'] = ('NTP_SERVERS=' + shlex.quote(' '.join(profile['ntp_servers'])) + '\n').encode()
    if inputs.get('pid1_runtime'):
        artifacts['core/lxc.container.conf'] += b'lxc.mount.entry = /ventuno-trial trial-status none bind,ro,create=dir 0 0\n'
    if autonomous:
        artifacts['core/lxc.container.conf'] += b'lxc.mount.entry = /ventuno-trial/control boot-control none bind,create=dir 0 0\n'
    if inputs.get('cgroup_v2'):
        artifacts['core/lxc.container.conf'] = artifacts['core/lxc.container.conf'].replace(
            b'lxc.cgroup.memory.limit_in_bytes', b'lxc.cgroup2.memory.max')
        artifacts['core/lxc.container.conf'] = artifacts['core/lxc.container.conf'].replace(b'cgroup:ro\n', b'cgroup:ro:force\n')
    if inputs.get('app_storage'):
        state['device.json']['disks'] = [{'name': 'nvme-apps', 'type': 'volume-disk'}]
        state['diagnostic/run.json']['storage']['data']['disk'] = 'nvme-apps'
        artifacts['core/lxc.container.conf'] = artifacts['core/lxc.container.conf'].replace(
            b'/storage/disks/perm/diagnostic/data', b'/mnt/appdata/perm/diagnostic/data')
    inputs['core_image'] = {
        'memory_limit': 536870912,
        'sha256': hashlib.sha256(artifacts['core/root.squashfs']).hexdigest(),
        'release': release,
        'package_manifest_sha256': hashlib.sha256((deploy / 'ventuno-core-image-ventuno-q.manifest').read_bytes()).hexdigest(),
    }
if args.core_only:
    assert inputs.get('revision_network')
    state = {key: value for key, value in state.items() if not key.startswith('diagnostic/')}
    artifacts = {key: value for key, value in artifacts.items() if not key.startswith('diagnostic/')}
    state['device.json']['groups'] = [group for group in state['device.json']['groups'] if group['name'] != 'app']
    state['device.json'].pop('disks', None)
    artifacts['core/lxc.container.conf'] = b'\n'.join(line for line in artifacts['core/lxc.container.conf'].split(b'\n') if b' diagnostic-data ' not in line)
    inputs['core_only'] = True
if args.k0s:
    assert args.core_only and inputs.get('cgroup_v2')
    from k0s_revision import add_k0s
    state, objects = add_k0s(state, artifacts['core/lxc.container.conf'],
                           (ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q/ventuno-k0s-image-ventuno-q.squashfs').read_bytes(),
                           inputs['kernel_release'], memory_kib=args.memory_kib)
    for name, digest in state.items():
        if isinstance(digest, str) and digest in objects: artifacts[name] = objects[digest]
    inputs['core_only'] = False
    inputs['k0s'] = {'version': 'v1.36.4+k0s.1', 'rootfs_sha256': state['k0s/root.squashfs']}
    from resource_policy import memory_budget
    inputs['resource_policy'] = memory_budget(args.memory_kib) if args.memory_kib else memory_budget()
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='pvstore-seed-') as temp:
    root = Path(temp)
    for name in ('objects', 'trails/0/.pvr', 'trails/0/.pv', 'cache', 'config', 'logs', 'disks'):
        (root / name).mkdir(parents=True, exist_ok=True)
    if autonomous:
        (root / 'boot').symlink_to('/mnt/ubuntu-trial/boot/pantavisor/state')
    else:
        (root / 'boot').mkdir()
    # The read-only diagnostic bind in core must exist before the app group starts.
    if inputs.get('app_storage'):
        backing = root / 'pv/volume-disk'
        backing.mkdir(parents=True)
        (backing / 'nvme-apps').symlink_to('/mnt/appdata')
    else:
        (root / 'disks/perm/diagnostic/data').mkdir(parents=True)
    for path, data in artifacts.items():
        digest = hashlib.sha256(data).hexdigest()
        state[path] = digest
        obj = root / 'objects' / digest
        if not obj.exists(): obj.write_bytes(data)
        if path.endswith(('authorized_keys', 'dropbear_ed25519_host_key')): obj.chmod(0o600)
        target = root / 'trails/0' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(obj, target)
    for path, value in state.items():
        if isinstance(value, dict):
            target = root / 'trails/0' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            # Pantavisor compares inline JSON bytes literally (including whitespace).
            target.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')))
    state_bytes = (json.dumps(state, sort_keys=True, separators=(',', ':')) + '\n').encode()
    (root / 'trails/0/.pvr/json').write_bytes(state_bytes)
    (root / 'trails/0/.pvr/config').write_text('{"#spec":"pvr-repo@1"}\n')
    env = b'# GRUB Environment Block\npv_rev=0\n'
    bootenv = env + b'#' * (1024 - len(env))
    if autonomous: (output / 'boot-state.grubenv').write_bytes(bootenv)
    else: (root / 'boot/grubenv').write_bytes(bootenv)
    image = output / 'pvstore.ext4'
    if image.exists():
        if not args.replace_seed:
            raise SystemExit(f'Refusing to overwrite an existing store: {image}')
        with image.open('rb') as stream:
            record = json.loads((output / 'pvstore-seed.json').read_text()) if (output / 'pvstore-seed.json').exists() else inputs['runtime_storage']
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], 'Seed has changed; preserve it'
        image.unlink()
    with image.open('wb') as stream: stream.truncate(size_mib * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-L', 'pvstore' if autonomous else 'pvstore-lab', '-E', 'lazy_itable_init=0,lazy_journal_init=0',
                    '-d', str(root), str(image)], check=True)
    if inputs.get('revision_network'):
        # mkfs -d preserves the rootless builder's uid. Dropbear requires
        # authorized_keys to belong to root; hardlinked objects share this inode.
        for name in ('home/root/.ssh/authorized_keys', 'etc/dropbear/dropbear_ed25519_host_key'):
            for field in ('uid', 'gid'):
                subprocess.run(['debugfs', '-w', '-R', f'set_inode_field /trails/0/_config/core/{name} {field} 0', str(image)], check=True)
        # Config overlays preserve directory ownership too; rootless staging
        # must not make Dropbear's home/.ssh ancestors owned by the build user.
        for directory in (root / 'trails/0/_config/core').rglob('*'):
            if directory.is_dir():
                for field in ('uid', 'gid'):
                    path = '/' + str(directory.relative_to(root))
                    subprocess.run(['debugfs', '-w', '-R', f'set_inode_field {path} {field} 0', str(image)], check=True)
with image.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
with image.open('rb') as source, (output / 'pvstore.ext4.gz').open('wb') as raw:
    with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as dest: shutil.copyfileobj(source, dest)
(output / 'revision-0.json').write_bytes(state_bytes)
inputs['runtime_storage'] = {'revision': '0', 'size': image.stat().st_size, 'sha256': digest,
                             'state_sha256': hashlib.sha256(state_bytes).hexdigest()}
(output / 'pvstore-seed.json').write_text(json.dumps(inputs['runtime_storage'], indent=2) + '\n')
(output / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
print('Seeded revision 0; core_only:', args.core_only, 'store:', image, 'SHA256:', digest)
if inputs.get('core_image'):
    (output / 'core-build.json').write_text(json.dumps(inputs['core_image'], indent=2) + '\n')
    print('Core:', release['version'], inputs['core_image']['sha256'])
