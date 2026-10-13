"""Manifest/config changes for the nested k0s system container."""
import copy
import hashlib
import re
from resource_policy import memory_budget


def add_k0s(base, core_config, rootfs, kernel_release, core_memory_limit=None, memory_kib=None):
    state = copy.deepcopy(base)
    assert {key for key in state if key.endswith('/run.json')} == {'bsp/run.json', 'core/run.json'}, 'Expected a core-only base'
    config = core_config.replace(b'lxc.cgroup.memory.limit_in_bytes', b'lxc.cgroup2.memory.max')
    config = config.replace(b'cgroup:ro\n', b'cgroup:ro:force\n')
    config = config.replace(b'/usr/sbin/ventuno-core-service', b'/usr/libexec/ventuno/core-init')
    if b'lxc.cgroup2.cpu.weight' not in config:
        config += b'lxc.cgroup2.cpu.weight = 200\n'
    if core_memory_limit is not None:
        assert isinstance(core_memory_limit, int) and core_memory_limit > 0
        config, count = re.subn(rb'(?m)^lxc\.cgroup2\.memory\.max\s*=\s*\d+$',
                               f'lxc.cgroup2.memory.max = {core_memory_limit}'.encode(), config)
        assert count == 1
    if b' k0s-access ' not in config:
        config += b'lxc.mount.entry = /mnt/appdata/perm/k0s/access k0s-access none bind,ro,optional,create=dir 0 0\n'
    budget = memory_budget(memory_kib) if memory_kib is not None else memory_budget()
    lxc = f'''lxc.uts.name = ventuno-k0s
lxc.init.cmd = /usr/sbin/init.lxc.static --name k0s -- /usr/libexec/ventuno/k0s-init
lxc.signal.halt = SIGTERM
lxc.rootfs.path = overlay:/volumes/k0s/root.squashfs:/volumes/k0s/lxc-overlay/upper
lxc.mount.auto = proc:rw sys:rw cgroup:rw:force
lxc.autodev = 1
lxc.tty.max = 0
lxc.pty.max = 16
lxc.console.path = none
lxc.apparmor.profile = unconfined
lxc.net.0.type = none
lxc.cap.drop = sys_boot sys_time
lxc.cgroup2.memory.max = {budget['k0s_memory_max']}
lxc.cgroup2.memory.high = {budget['k0s_memory_high']}
lxc.cgroup2.pids.max = 8192
lxc.cgroup2.devices.allow = a
lxc.mount.entry = /mnt/appdata/perm/k0s/data var/lib/k0s none rbind,create=dir 0 0
lxc.mount.entry = /mnt/appdata/perm/k0s/workloads data none rbind,create=dir 0 0
lxc.mount.entry = /mnt/appdata/perm/k0s/access access none bind,create=dir 0 0
lxc.mount.entry = /mnt/appdata/perm/k0s/log var/log none rbind,create=dir 0 0
lxc.mount.entry = /lib/modules lib/modules none bind,ro,create=dir 0 0
lxc.mount.entry = /dev/kmsg dev/kmsg none bind,ro,create=file 0 0
lxc.mount.entry = /ventuno-trial/control clock-status none bind,ro,create=dir 0 0
lxc.mount.entry = /boot/config-{kernel_release} boot/config-{kernel_release} none bind,ro,create=file 0 0
lxc.mount.entry = tmpfs run tmpfs nosuid,nodev,mode=0755,create=dir 0 0
lxc.mount.entry = tmpfs tmp tmpfs nosuid,nodev,mode=1777,create=dir 0 0
lxc.mount.entry = tmpfs dev/shm tmpfs nosuid,nodev,mode=1777,size=64m,create=dir 0 0
'''.encode()
    objects = {}
    for name, data in [('core/lxc.container.conf', config), ('k0s/lxc.container.conf', lxc), ('k0s/root.squashfs', rootfs)]:
        digest = hashlib.sha256(data).hexdigest()
        state[name] = digest
        objects[digest] = data
    state['device.json']['groups'].append({'name': 'app', 'status_goal': 'STARTED', 'restart_policy': 'container', 'timeout': 60})
    state['k0s/run.json'] = {
        '#spec': 'service-manifest-run@1', 'name': 'k0s', 'type': 'lxc', 'group': 'app',
        'config': 'lxc.container.conf', 'root-volume': 'root.squashfs', 'volumes': [],
        'status_goal': 'STARTED', 'restart_policy': 'container', 'roles': ['nobody'],
        'storage': {'lxc-overlay': {'persistence': 'boot'}},
    }
    return state, objects


def replace_k0s(base, core_config, rootfs, kernel_release, core_memory_limit=None, memory_kib=None):
    assert {key for key in base if key.endswith('/run.json')} == {'bsp/run.json', 'core/run.json', 'k0s/run.json'}
    state = copy.deepcopy(base)
    for key in list(state):
        if key.startswith(('k0s/', '_config/k0s/')): del state[key]
    state['device.json']['groups'] = [group for group in state['device.json']['groups'] if group['name'] != 'app']
    return add_k0s(state, core_config, rootfs, kernel_release, core_memory_limit, memory_kib)
