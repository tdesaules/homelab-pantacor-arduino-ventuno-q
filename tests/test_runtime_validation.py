from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from runtime_validation import is_ready, is_stopped, network_ready, core_ready, host_pid1_ready


class RuntimeStatusTests(unittest.TestCase):
    def test_pid1_requires_observed_executable_and_separate_guardian(self):
        text = ('### Host PID 1\nhost_pid1_name=pantavisor\n'
                'host_pid1_exe=/usr/bin/pantavisor\npantavisor_pid=1\n'
                'supervisor_version=3\nguardian_pid=10\n')
        self.assertTrue(host_pid1_ready(text))
        self.assertFalse(host_pid1_ready(text.replace('host_pid1_name=pantavisor', 'host_pid1_name=ventuno-init')))
        self.assertFalse(host_pid1_ready(text.replace('/usr/bin/pantavisor', '/bin/busybox')))
        self.assertFalse(host_pid1_ready(text.replace('guardian_pid=10', 'guardian_pid=1')))
        self.assertFalse(host_pid1_ready(''))

    def output(self, status='READY', stopped='false'):
        return ('### Pantavisor containers\n'
                '[{"name":"diagnostic","status":"' + status + '","status_goal":"READY","user_stopped":"' + stopped + '"}]\n'
                '### Revision progress\n{"status":"DONE"}\n'
                '### Persistent application data\n2\n'
                '{"container":"diagnostic","pid":1,"starts":2}\n')

    def test_ready_requires_actual_state_not_goal(self):
        self.assertTrue(is_ready(self.output(), 2))
        self.assertFalse(is_ready(self.output('STARTING'), 2))
        self.assertFalse(is_ready(self.output(), 1))

    def test_stop_requires_completion(self):
        self.assertFalse(is_stopped(self.output('STOPPING', 'true')))
        self.assertTrue(is_stopped(self.output('STOPPED', 'true')))

    def test_missing_response_is_not_success(self):
        self.assertFalse(is_ready('ERROR: socket not found', 1))

    def test_network_restart_requires_new_counter_and_actual_ready(self):
        text = ('### Pantavisor containers\n'
                '[{"name":"diagnostic","status":"READY"},'
                '{"name":"network","status":"READY","status_goal":"READY"}]\n'
                '### Revision network\nNETWORK_STARTS=2\n'
                'DHCP_BOUND=1\nNETWORK_OWNER=revision\n')
        self.assertTrue(network_ready(text, 2))
        self.assertFalse(network_ready(text, 1))
        self.assertFalse(network_ready(text.replace('"network","status":"READY"',
                                                    '"network","status":"STARTING"'), 2))
        self.assertFalse(network_ready(text.replace('DHCP_BOUND=1', ''), 2))

    def test_core_requires_roles_denied_app_access_and_matching_release(self):
        release = {'name': 'ventuno-core', 'version': '0.1.0'}
        text = ('### Pantavisor containers\n'
                '[{"name":"diagnostic","group":"app","roles":["nobody"]},'
                '{"name":"core","group":"root","roles":["mgmt"],"status":"READY"}]\n'
                '### Persistent application data\n1\n{"management_http_status":403}\n'
                '### Core\nCORE_STARTS=2\nDHCP_BOUND=1\nNETWORK_OWNER=core\n'
                '### Core release\n{"name":"ventuno-core","version":"0.1.0"}\n')
        self.assertTrue(core_ready(text, 2, release))
        self.assertTrue(core_ready(text.replace('["nobody"]', '[]'), 2, release))
        self.assertFalse(core_ready(text, 1, release))
        self.assertFalse(core_ready(text.replace('403', '200'), 2, release))
        self.assertFalse(core_ready(text.replace('nobody', 'mgmt'), 2, release))
        self.assertFalse(core_ready(text.replace('READY', 'STARTING'), 2, release))
        self.assertFalse(core_ready(text, 2, release | {'version': '0.2.0'}))
