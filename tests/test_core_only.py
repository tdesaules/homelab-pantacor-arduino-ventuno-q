import hashlib
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from core_only import make_core_only


class CoreOnlyTests(unittest.TestCase):
    def test_only_diagnostic_is_removed_and_bsp_is_preserved(self):
        config = b'lxc.net.0.type = none\nlxc.mount.entry = /mnt/appdata/perm/diagnostic/data diagnostic-data none bind,ro,create=dir 0 0\n'
        base = {'#spec': 'pantavisor-service-system@1', 'bsp/run.json': {'linux': 'kernel.img'},
                'bsp/kernel.img': 'kernel-hash', 'bsp/pantavisor': 'initrd-hash',
                'core/run.json': {'name': 'core', 'type': 'lxc'},
                'core/lxc.container.conf': hashlib.sha256(config).hexdigest(), 'core/root.squashfs': 'old-core',
                'diagnostic/run.json': {'name': 'diagnostic', 'type': 'lxc'}, 'diagnostic/root.squashfs': 'app',
                'device.json': {'groups': [{'name': 'root'}, {'name': 'app'}],
                                'disks': [{'name': 'nvme-apps', 'type': 'volume-disk'}]}}
        state, objects = make_core_only(base, config, b'new-core')
        self.assertNotIn('diagnostic/run.json', state)
        self.assertIn('diagnostic/run.json', base)
        self.assertEqual(state['bsp/pantavisor'], base['bsp/pantavisor'])
        self.assertEqual(state['device.json'], {'groups': [{'name': 'root'}]})
        self.assertNotIn(b'diagnostic-data', objects[state['core/lxc.container.conf']])
        base['other/run.json'] = {'name': 'other', 'type': 'lxc'}
        with self.assertRaises(ValueError): make_core_only(base, config, b'new-core')
