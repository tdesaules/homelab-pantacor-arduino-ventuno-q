import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from nvme_validation import validate_nvme


class NvmeValidationTests(unittest.TestCase):
    identity = '12345678-1234-1234-1234-123456789abc'
    filesystem = '87654321-1234-1234-1234-123456789abc'
    release = {'name': 'ventuno-core', 'version': '0.1.2'}
    inputs = {'core_image': {'release': release}, 'app_storage': {'filesystem_uuid': filesystem}}

    def output(self):
        return ('### Pantavisor containers\n'
                '[{"name":"core","group":"root","status":"READY","roles":["mgmt"]},'
                '{"name":"diagnostic","group":"app","status":"READY","roles":[]}]\n'
                '### Revision progress\n{"status":"DONE"}\n'
                '### Persistent application data\n2\n' + json.dumps({'container': 'diagnostic', 'pid': 1, 'starts': 2,
                 'management_http_status': 403, 'identity': self.identity}) + '\n'
                '### Core\nCORE_STARTS=1\nDHCP_BOUND=1\nNETWORK_OWNER=core\n'
                '### Core release\n' + json.dumps(self.release) + '\n'
                '### Host PID 1\nsupervisor_version=4\npantavisor_pid=1\n'
                'host_pid1_name=pantavisor\nhost_pid1_exe=/usr/bin/pantavisor\nguardian_pid=10\n'
                '### Application storage\nAPPDATA_MOUNTED=1\nAPPDATA_UUID=' + self.filesystem + '\n'
                'APPDATA_FILESYSTEM=ext4\nAPPDATA_DEVICE=/dev/nvme0n1p1\n'
                'Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/nvme0n1p1 262144 65536 196608 25% /diagnostic-data\n')

    def test_second_boot_retains_identity_on_expected_filesystem(self):
        result = validate_nvme(self.output(), self.inputs, 2, self.identity)
        self.assertEqual(result['application_identity'], self.identity)

    def test_wrong_disk_identity_and_counter_fail(self):
        for text, starts, identity in (
            (self.output().replace(self.filesystem, self.identity), 2, self.identity),
            (self.output().replace('/dev/nvme0n1p1', '/dev/loop32'), 2, self.identity),
            (self.output().replace('/dev/nvme0n1p1', '/dev/mmcblk0p71'), 2, self.identity),
            (self.output(), 1, self.identity), (self.output(), 2, self.filesystem),
        ):
            with self.subTest(starts=starts, identity=identity), self.assertRaises(ValueError):
                validate_nvme(text, self.inputs, starts, identity)
