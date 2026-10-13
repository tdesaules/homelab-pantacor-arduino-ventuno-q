from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lab'))
from autonomous_boot import grub_default, grub_entry
from revision_names import valid_revision
from tools.pvbuild.host import grub_checker


class RevisionNameTests(unittest.TestCase):
    def test_release_names_and_historical_revisions(self):
        for name in ('0', 'locals/0.1.0', 'locals/v0.1.0', 'locals/0.1.0-rc.1',
                     'locals/k0s-os-070', 'locals/' + 'a' * 64):
            with self.subTest(name=name): self.assertTrue(valid_revision(name))
        self.assertFalse(valid_revision('0', allow_factory=False))

    def test_rejects_traversal_injection_and_overlong_suffixes(self):
        for name in ('', '0.1.0', 'v0.1.0', 'locals/', 'locals/.', 'locals/..',
                     'locals/../x', 'locals/x/y', 'locals/x panic=0', 'locals/x\nreboot',
                     'locals/x;reboot', 'locals/$(reboot)', 'locals/-x',
                     'locals/' + 'a' * 65, 'locals/sha256-' + 'a' * 64):
            with self.subTest(name=name): self.assertFalse(valid_revision(name))

    def test_grub_guards_use_the_same_revision_rules(self):
        uuid = '12345678-1234-1234-1234-123456789abc'
        text = grub_default(uuid) + grub_entry(uuid, 'a' * 32)
        patterns = re.findall(r"regexp '([^']+)' \"\$(pv_rev|pv_try)\"", text)
        self.assertEqual([variable for _, variable in patterns].count('pv_rev'), 2)
        self.assertEqual([variable for _, variable in patterns].count('pv_try'), 1)
        for pattern, _ in patterns:
            for name in ('0', 'locals/0.1.0', 'locals/..', 'locals/x/y', 'locals/' + 'a' * 65):
                self.assertEqual(re.fullmatch(pattern, name) is not None, valid_revision(name))
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='release-grub-') as directory:
            config = Path(directory) / 'grub.cfg'
            config.write_text(text)
            subprocess.run([grub_checker(), str(config)], check=True)

    def test_invalid_upgrade_revision_is_rejected_before_accessing_board_or_inputs(self):
        result = subprocess.run([sys.executable, str(ROOT / 'lab/prepare-runtime-upgrade.py'),
                                 '--output-dir', '/nonexistent', '--revision', 'locals/../x'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Invalid local revision', result.stderr)
