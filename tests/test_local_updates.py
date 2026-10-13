import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from local_updates import Session, update_ready


class LocalUpdateTests(unittest.TestCase):
    release = {'name': 'ventuno-core', 'version': '0.2.0'}
    inputs = {'core_image': {'release': release}}
    identity = '12345678-1234-1234-1234-123456789abc'

    def output(self):
        return ('### Pantavisor containers\n'
                '[{"name":"core","group":"root","status":"READY","roles":["mgmt"]},'
                '{"name":"diagnostic","group":"app","status":"READY","status_goal":"READY","roles":[]}]\n'
                '### Running revision\nlocals/app-v2\n'
                '### Revision progress\n{"status":"UPDATED"}\n'
                '### Persistent application data\n4\n' + json.dumps({'container': 'diagnostic', 'pid': 1, 'starts': 4,
                 'management_http_status': 403, 'identity': self.identity, 'application_version': '2.0.0'}) + '\n'
                '### Core\nCORE_STARTS=1\nDHCP_BOUND=1\nNETWORK_OWNER=core\n'
                '### Core release\n' + json.dumps(self.release) + '\n'
                '### Host PID 1\nsupervisor_version=4\npantavisor_pid=1\n'
                'host_pid1_name=pantavisor\nhost_pid1_exe=/usr/bin/pantavisor\nguardian_pid=10\n')

    def ready(self, text):
        return update_ready(text, self.inputs, 'locals/app-v2', '2.0.0', 4, self.identity)

    def test_only_stable_expected_revision_and_binary_version_are_accepted(self):
        text = self.output()
        self.assertTrue(self.ready(text))
        self.assertTrue(self.ready(text.replace('UPDATED', 'DONE')))
        for old, new in (('UPDATED', 'TESTING'), ('locals/app-v2', 'locals/app-v1'),
                         ('2.0.0', '1.0.0'), ('CORE_STARTS=1', 'CORE_STARTS=2'),
                         (self.identity, 'another-identity'), ('"starts": 4', '"starts": 5'),
                         ('"status":"READY","status_goal"', '"status":"STARTING","status_goal"')):
            with self.subTest(old=old): self.assertFalse(self.ready(text.replace(old, new)))

    def test_transient_progress_read_is_retried_before_accepting_stable_state(self):
        session = Session('unused', 0, Path('.'))
        session.snapshot = Mock(side_effect=[RuntimeError('temporary progress 404'),
                                            self.output().replace('UPDATED', 'TESTING'), self.output()])
        with patch('local_updates.time.sleep'):
            text = session.wait_ready('test', self.inputs, 'locals/app-v2', '2.0.0', 4, self.identity)
        self.assertEqual(text, self.output())
        self.assertEqual(session.snapshot.call_count, 3)

    def test_unready_observation_retries_and_retains_scenario_before_request(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root / 'artifacts', prefix='test-update-') as work:
            directory = Path(work)
            session = Session('unused', 0, directory)
            previous = {'last_good_revision': 'locals/app-v2', 'failed_revision': 'locals/app-unready',
                        'expected_after_commit_boot': 4, 'application_identity': self.identity}
            session.wait_ready = Mock(return_value=self.output().replace('UPDATED', 'DONE'))
            session.shells = Mock()
            session.control = Mock(side_effect=lambda *args: self.assertTrue((directory / 'updates-result.json').exists()))
            bad = self.output().replace('2.0.0', '2.0.0-unready').replace('"starts": 4', '"starts": 5')
            bad = bad.replace('"status":"READY","status_goal"', '"status":"STARTED","status_goal"')
            session.snapshot = Mock(side_effect=[RuntimeError('temporary progress 404'), bad])
            with patch('local_updates.time.sleep'):
                session.fail_after_commit(self.inputs, previous)
            session.control.assert_called_once_with('cmd', 'run', 'locals/app-unready')
            self.assertEqual(session.snapshot.call_count, 2)

    def test_reboot_disconnect_is_recorded_without_resending_command(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root / 'artifacts', prefix='test-reboot-') as work:
            session = Session('unused', 0, Path(work))
            session.run = Mock(side_effect=RuntimeError('Connection closed by remote host'))
            session.reboot_command('ventuno-reboot ubuntu')
            session.run.assert_called_once_with('ventuno-reboot ubuntu')
            self.assertIn('ventuno-reboot ubuntu', (Path(work) / 'reboot-transport.log').read_text())
            session.run = Mock(side_effect=RuntimeError('HTTP 403: forbidden'))
            with self.assertRaises(RuntimeError): session.reboot_command('ventuno-reboot ubuntu')
