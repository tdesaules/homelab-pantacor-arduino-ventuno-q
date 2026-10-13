import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from soak_validation import validate_snapshot


class SoakValidationTests(unittest.TestCase):
    trial = 'a' * 32
    release = {'name': 'ventuno-core', 'version': '0.1.1'}
    inputs = {'core_image': {'release': release}}

    def snapshot(self):
        return ('### Kernel command line\nventuno_trial=' + self.trial + '\n'
                '### Boot ID\n12345678-1234-1234-1234-123456789abc\n'
                '### Pantavisor containers\n'
                '[{"name":"core","group":"root","status":"READY","roles":["mgmt"]},'
                '{"name":"diagnostic","group":"app","status":"READY","roles":[]}]\n'
                '### Revision progress\n{"status":"DONE"}\n'
                '### Persistent application data\n1\n'
                '{"container":"diagnostic","pid":1,"starts":1,"uptime":99,"management_http_status":403}\n'
                '### Core\nCORE_STARTS=1\nDHCP_BOUND=1\nNETWORK_OWNER=core\n'
                '### Core release\n' + json.dumps(self.release) + '\n'
                '### Host PID 1\nsupervisor_version=4\npantavisor_pid=1\n'
                'host_pid1_name=pantavisor\nhost_pid1_exe=/usr/bin/pantavisor\n'
                'guardian_pid=10\nreturn_after=900\nelapsed=97\nwatchdog=armed\nwatchdog_timeout=30\n'
                '### Uptime\n100.5 10.0\n### Memory\nMemAvailable: 524288 kB\n'
                '### Storage\nFilesystem 1024-blocks Used Available Capacity Mounted\n/dev/loop32 262144 65536 196608 25% /data\n'
                '### Load\n0.1 0.2 0.3 1/10 50\n### Thermal\nnone\ncpu 45000\n'
                '### Kernel anomalies\nnone\n')

    def validate(self, text, previous=None):
        return validate_snapshot(text, self.trial, self.inputs, 900, True, previous)

    def test_good_snapshot_and_temperature(self):
        sample = self.validate(self.snapshot())
        self.assertEqual(sample['heartbeat_lag'], 1.5)
        self.assertEqual(sample['temperatures_millicelsius']['cpu'], 45000)

    def test_stale_heartbeat_restart_and_resources_fail(self):
        for old, new in (('"uptime":99', '"uptime":70'), ('CORE_STARTS=1', 'CORE_STARTS=2'),
                         ('524288 kB', '1024 kB'), ('196608 25%', '1024 99%'),
                         ('watchdog=armed', 'watchdog=unavailable'), ('return_after=900', 'return_after=180'),
                         ('### Kernel anomalies\nnone', '### Kernel anomalies\nEXT4-fs error')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.validate(self.snapshot().replace(old, new))

    def test_stalled_guardian_and_changed_boot_fail(self):
        first = self.validate(self.snapshot())
        with self.assertRaises(ValueError): self.validate(self.snapshot(), first)
        updated = self.snapshot().replace('elapsed=97', 'elapsed=112').replace('100.5 10.0', '115.5 10.0').replace('"uptime":99', '"uptime":114')
        self.validate(updated, first)
        with self.assertRaises(ValueError): self.validate(updated.replace('guardian_pid=10', 'guardian_pid=20'), first)
        with self.assertRaises(ValueError): self.validate(updated.replace('123456789abc', '123456789def'), first)
