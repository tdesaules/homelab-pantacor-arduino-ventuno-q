"""Build and validate a core-only state without deleting persistent application data."""
import copy
import hashlib
import json
from runtime_validation import host_pid1_ready, section


def make_core_only(base, config, rootfs):
    platforms = {value['name'] for key, value in base.items()
                 if key.endswith('/run.json') and isinstance(value, dict) and value.get('type') == 'lxc'}
    if not platforms <= {'core', 'diagnostic'} or 'core' not in platforms:
        raise ValueError('Unexpected applications: refusing to replace an unrelated deployment')
    if hashlib.sha256(config).hexdigest() != base['core/lxc.container.conf']:
        raise ValueError('Base core configuration hash mismatch')
    state = copy.deepcopy(base)
    for key in list(state):
        if key.startswith(('diagnostic/', '_config/diagnostic/')): del state[key]
    state['device.json']['groups'] = [group for group in state['device.json']['groups'] if group['name'] != 'app']
    disks = state['device.json'].get('disks', [])
    if any(disk['name'] != 'nvme-apps' for disk in disks):
        raise ValueError('Unexpected logical disk')
    state['device.json'].pop('disks', None)
    config = b'\n'.join(line for line in config.splitlines() if b' diagnostic-data ' not in line) + b'\n'
    objects = {hashlib.sha256(config).hexdigest(): config, hashlib.sha256(rootfs).hexdigest(): rootfs}
    state['core/lxc.container.conf'] = hashlib.sha256(config).hexdigest()
    state['core/root.squashfs'] = hashlib.sha256(rootfs).hexdigest()
    assert state['bsp/run.json'] == base['bsp/run.json']
    assert all(state[key] == value for key, value in base.items() if key.startswith('bsp/'))
    return state, objects


def core_only_ready(text, revision, release):
    try:
        containers, _ = json.JSONDecoder().raw_decode(section(text, '### Pantavisor containers'))
        progress, _ = json.JSONDecoder().raw_decode(section(text, '### Revision progress'))
        current, _ = json.JSONDecoder().raw_decode(section(text, '### Current revision'))
        actual, _ = json.JSONDecoder().raw_decode(section(text, '### Core release'))
        running = section(text, '### Running revision').splitlines()[0].strip('"')
        return (len(containers) == 1 and containers[0]['name'] == 'core' and containers[0]['status'] == 'READY'
                and containers[0]['roles'] == ['mgmt'] and progress['status'] == 'DONE'
                and running == revision and actual == release and host_pid1_ready(text)
                and not any(key.startswith(('diagnostic/', '_config/diagnostic/')) for key in current)
                and '### Persistent application data' not in text)
    except (ValueError, KeyError, IndexError, TypeError):
        return False
