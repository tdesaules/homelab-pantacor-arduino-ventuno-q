import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GrubDurationTests(unittest.TestCase):
    def generate(self, **overrides):
        inputs = {'kernel_release': '6.8.0-1084-qcom', 'bounded_trial': True,
                  'pid1_runtime': True, 'trial_supervisor_version': 4,
                  'trial_max_seconds': 1800} | overrides
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='test-grub-') as work:
            directory = Path(work)
            (directory / 'build-inputs.json').write_text(json.dumps(inputs))
            result = subprocess.run([
                sys.executable, str(ROOT / 'lab/generate-grub-entry.py'),
                '--rootfs-uuid', '12345678-1234-1234-1234-123456789abc',
                '--trial-id', '0123456789abcdef0123456789abcdef', '--output-dir', str(directory),
            ], capture_output=True, text=True)
            stanza = directory / 'grub-diagnostic.cfg'
            return result.returncode, stanza.read_text() if stanza.exists() else ''

    def test_default_and_extended_deadline_reach_kernel_command_line(self):
        for duration in (180, 900, 1800):
            with self.subTest(duration=duration):
                code, text = self.generate(trial_return_seconds=duration)
                self.assertEqual(code, 0)
                linux = next(line for line in text.splitlines() if line.strip().startswith('linux '))
                self.assertIn(f'ventuno_return_seconds={duration}', linux.split())
                self.assertIn('ventuno_trial=0123456789abcdef0123456789abcdef', linux.split())
        code, text = self.generate()
        self.assertEqual(code, 0)
        self.assertIn('ventuno_return_seconds=180', text)

    def test_old_guardian_and_out_of_range_duration_are_rejected(self):
        cases = ({'trial_supervisor_version': 3, 'trial_return_seconds': 900},
                 {'trial_max_seconds': 9999, 'trial_return_seconds': 1801},
                 {'trial_return_seconds': 0}, {'trial_return_seconds': '900'})
        for case in cases:
            with self.subTest(case=case):
                code, text = self.generate(**case)
                self.assertNotEqual(code, 0)
                self.assertEqual(text, '')

    def test_revision_selection_is_explicit_and_rejects_path_or_command_injection(self):
        for revision in ('locals/app-v2', 'locals/0.1.0'):
            code, text = self.generate(boot_revision=revision)
            self.assertEqual(code, 0)
            linux = next(line for line in text.splitlines() if line.strip().startswith('linux '))
            self.assertIn('pv_rev=' + revision, linux.split())
        for invalid in ('../0', 'locals/../../0', 'locals/x panic=0', 'locals/x\nreboot',
                        'locals/..', 'locals/' + 'a' * 65):
            with self.subTest(invalid=invalid):
                code, text = self.generate(boot_revision=invalid)
                self.assertNotEqual(code, 0)
                self.assertEqual(text, '')
