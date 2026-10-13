#!/usr/bin/env python3
"""Validate the ext4 seed against Pantavisor's literal JSON/object contract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/prototype-1084-runtime')
args = parser.parse_args()
output = args.output_dir
inputs = json.loads((output / 'build-inputs.json').read_text())
image = output / 'pvstore.ext4'
with image.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == inputs['runtime_storage']['sha256']

def read(path):
    return subprocess.check_output(['debugfs', '-R', 'cat ' + path, str(image)], stderr=subprocess.DEVNULL)

data = read('/trails/0/.pvr/json')
assert hashlib.sha256(data).hexdigest() == inputs['runtime_storage']['state_sha256']
state = json.loads(data)
assert state['#spec'] == 'pantavisor-service-system@1'
if inputs.get('autonomous_boot'):
    link = subprocess.check_output(['debugfs', '-R', 'stat /boot', str(image)], stderr=subprocess.DEVNULL, text=True)
    assert 'Type: symlink' in link and '/mnt/ubuntu-trial/boot/pantavisor/state' in link
    assert inputs['runtime_storage']['size'] == 1024 * 1024 * 1024
    env = (output / 'boot-state.grubenv').read_bytes()
    assert len(env) == 1024 and env.startswith(b'# GRUB Environment Block\npv_rev=0\n')
if inputs.get('app_storage'):
    assert state['device.json']['disks'] == [{'name': 'nvme-apps', 'type': 'volume-disk'}]
    assert state['diagnostic/run.json']['storage']['data'] == {'persistence': 'permanent', 'disk': 'nvme-apps'}
    assert b'/mnt/appdata/perm/diagnostic/data diagnostic-data' in read('/trails/0/core/lxc.container.conf')
    link = subprocess.check_output(['debugfs', '-R', 'stat /pv/volume-disk/nvme-apps', str(image)], stderr=subprocess.DEVNULL, text=True)
    assert 'Type: symlink' in link and '"/mnt/appdata"' in link, link
    fallback = subprocess.check_output(['debugfs', '-R', 'stat /disks/perm/diagnostic/data', str(image)], stderr=subprocess.DEVNULL, text=True)
    assert 'Inode:' not in fallback, 'Unexpected eMMC application fallback'
    print('PASS: NVMe bind-backed disk, explicit application volume and no eMMC fallback directory')
if inputs.get('revision_network'):
    component = inputs.get('management_container') or 'network'
    network = state[component + '/run.json']
    assert network['type'] == 'lxc' and network['status_goal'] == 'READY'
    lxc = read(f'/trails/0/{component}/lxc.container.conf').decode()
    assert 'lxc.net.0.type = none' in lxc
    assert f'init.lxc.static --name {component} -- /usr/sbin/ventuno-{component}-service' in lxc
    config_overlay = '_config/core/etc/ventuno-network.conf' in state
    authorized = '_config/core/home/root/.ssh/authorized_keys' if config_overlay else f'{component}/authorized_keys'
    hostkey = '_config/core/etc/dropbear/dropbear_ed25519_host_key' if config_overlay else f'{component}/host_key'
    if config_overlay: assert '/storage/trails/0/' not in lxc
    assert read('/trails/0/' + authorized).decode().strip() == inputs['network_profile']['client_public_key']
    details = subprocess.check_output(['debugfs', '-R', 'stat /trails/0/' + hostkey, str(image)], stderr=subprocess.DEVNULL, text=True)
    assert re.search(r'Mode:\s+0600\b', details), details
    for name in (authorized, hostkey):
        details = subprocess.check_output(['debugfs', '-R', 'stat /trails/0/' + name, str(image)], stderr=subprocess.DEVNULL, text=True)
        assert re.search(r'User:\s+0\s+Group:\s+0\b', details), details
    assert read(f'/trails/0/{component}/root.squashfs')[:4] == b'hsqs'
    if component == 'core':
        assert [g['name'] for g in state['device.json']['groups']] == ['root', 'app']
        assert network['group'] == 'root' and network['roles'] == ['mgmt']
        assert state['diagnostic/run.json']['group'] == 'app'
        assert state['diagnostic/run.json']['roles'] == ['nobody']
        assert state['core/root.squashfs'] == inputs['core_image']['sha256']
        release = inputs['core_image']['release']
        assert release['name'] == 'ventuno-core' and release['version']
        assert release['service_sources_sha256'] == hashlib.sha256(json.dumps(release['service_sources'], sort_keys=True).encode()).hexdigest()
        print('PASS: core/root/mgmt then diagnostic/app/nobody; core image and source identity recorded')
    print('PASS: revision-owned network manifest, rootfs, credentials and host network namespace')
for path, value in state.items():
    if path == '#spec': continue
    actual = read('/trails/0/' + path)
    if isinstance(value, dict):
        assert actual == json.dumps(value, sort_keys=True, separators=(',', ':')).encode(), path
    else:
        assert hashlib.sha256(actual).hexdigest() == value, path
        assert hashlib.sha256(read('/objects/' + value)).hexdigest() == value
        details = subprocess.check_output(['debugfs', '-R', 'stat /objects/' + value, str(image)], stderr=subprocess.DEVNULL, text=True)
        assert int(re.search(r'Links:\s+(\d+)', details).group(1)) >= 2, path
subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)
print('PASS: ext4 seed, literal JSON, SHA-256 objects and hardlink retention')
