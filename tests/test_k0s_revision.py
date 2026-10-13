import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from k0s_revision import add_k0s, replace_k0s


class K0sRevisionTests(unittest.TestCase):
    def test_preserves_bsp_credentials_and_requires_nvme_for_cluster(self):
        base = {'bsp/run.json': {'linux': 'kernel.img'}, 'bsp/kernel.img': 'kernel-digest',
                'bsp/pantavisor': 'initramfs-digest', 'core/run.json': {'roles': ['mgmt']},
                '_config/core/authorized_keys': 'key-digest',
                'device.json': {'groups': [{'name': 'root'}]}}
        original = copy.deepcopy(base)
        config = b'lxc.mount.auto = proc:mixed sys:ro cgroup:ro\nlxc.cgroup.memory.limit_in_bytes = 268435456\n'
        state, objects = add_k0s(base, config, b'rootfs', '6.8.0-test')
        self.assertEqual(base, original)
        for key in ('bsp/run.json', 'bsp/kernel.img', 'bsp/pantavisor', 'core/run.json', '_config/core/authorized_keys'):
            self.assertEqual(state[key], base[key])
        for digest, data in objects.items(): self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        core = objects[state['core/lxc.container.conf']].decode()
        self.assertIn('cgroup:ro:force', core)
        self.assertIn('lxc.cgroup2.memory.max = 268435456', core)
        cluster = objects[state['k0s/lxc.container.conf']].decode()
        mounts = [line for line in cluster.splitlines() if '/mnt/appdata/' in line]
        self.assertEqual(len(mounts), 4)
        self.assertTrue(all('optional' not in line for line in mounts))
        self.assertEqual(state['k0s/run.json']['roles'], ['nobody'])

    def test_rejects_an_existing_application_deployment(self):
        with self.assertRaises(AssertionError):
            add_k0s({'bsp/run.json': {}, 'core/run.json': {}, 'other/run.json': {}}, b'', b'', 'test')

    def test_image_replacement_keeps_bsp_and_does_not_duplicate_groups_or_binds(self):
        base = {'bsp/run.json': {}, 'bsp/pantavisor': 'fixed', 'core/run.json': {},
                'device.json': {'groups': [{'name': 'root'}]}}
        first, objects = add_k0s(base, b'core-config\n', b'first', 'test')
        updated, added = replace_k0s(first, objects[first['core/lxc.container.conf']], b'second', 'test')
        self.assertEqual(updated['bsp/pantavisor'], 'fixed')
        self.assertEqual([group['name'] for group in updated['device.json']['groups']], ['root', 'app'])
        self.assertEqual(added[updated['core/lxc.container.conf']].count(b' k0s-access '), 1)
        self.assertNotEqual(first['k0s/root.squashfs'], updated['k0s/root.squashfs'])

    def test_management_budget_can_change_without_changing_cluster_configuration(self):
        base = {'bsp/run.json': {}, 'bsp/pantavisor': 'fixed', 'core/run.json': {},
                'device.json': {'groups': [{'name': 'root'}]}}
        config = b'lxc.cgroup2.memory.max = 268435456\n'
        first, objects = add_k0s(base, config, b'cluster', 'test')
        updated, added = replace_k0s(first, objects[first['core/lxc.container.conf']], b'cluster', 'test', 536870912)
        self.assertEqual({key for key in first if first[key] != updated[key]}, {'core/lxc.container.conf'})
        self.assertIn(b'lxc.cgroup2.memory.max = 536870912', added[updated['core/lxc.container.conf']])
