from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from autonomous_boot import grub_entry, grubenv
from tools.pvbuild.host import grub_checker


class AutonomousBootTests(unittest.TestCase):
    def test_stable_entry_uses_external_state_and_single_attempt(self):
        entry = grub_entry('12345678-1234-1234-1234-123456789abc', 'a' * 32)
        self.assertIn('pv_rev=$ventuno_selected', entry)
        self.assertIn('ventuno_attempt="$pv_try"', entry)
        self.assertIn('PANTAVISOR_BOOT_BUDGET_EXHAUSTED', entry)
        self.assertNotIn('ventuno_return_seconds', entry)
        self.assertNotIn('set default=', entry)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'artifacts', prefix='test-auto-') as work:
            path = Path(work) / 'entry.cfg'
            path.write_text(entry)
            subprocess.run([grub_checker(), str(path)], check=True)

    def test_invalid_install_identity_is_rejected(self):
        for identity in ('../x', 'a' * 31, 'a' * 32 + ' reboot'):
            with self.assertRaises(ValueError):
                grub_entry('12345678-1234-1234-1234-123456789abc', identity)

    def test_environment_is_a_real_fixed_size_grub_block(self):
        block = grubenv({'pv_rev': 'locals/app-v2', 'ventuno_boots': '0'})
        self.assertEqual(len(block), 1024)
        self.assertTrue(block.startswith(b'# GRUB Environment Block\n'))
        self.assertIn(b'pv_rev=locals/app-v2\n', block)

    def test_fault_injection_is_not_generated_for_hardware(self):
        args = ('12345678-1234-1234-1234-123456789abc', 'a' * 32)
        with self.assertRaises(ValueError): grub_entry(*args, stall_bootstrap=True)
        self.assertIn('ventuno_pid1_test_stall=1', grub_entry(*args, emulated=True, stall_bootstrap=True))
