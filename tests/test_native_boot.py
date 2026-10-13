import subprocess
import stat
import tempfile
from pathlib import Path
import unittest

from tools.pvbuild.host import grub_checker
from tools.pvbuild.model import ROOT, compose
from tools.pvbuild.native import esp_bootstrap, native_grub, require_recovery_tools


class NativeBootTests(unittest.TestCase):
    def test_esp_dispatcher_never_requires_the_system_partition(self):
        text = esp_bootstrap('78B2-3FE4', 'ventuno-native-test')
        self.assertNotIn('/boot/grub', text)
        self.assertNotIn('configfile', text)
        self.assertIn('/EFI/ventuno-native-test/recoveryaa64.efi', text)
        with self.assertRaises(ValueError): esp_bootstrap('78B2-3FE4', '../ubuntu')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'grub.cfg'
            path.write_text(text)
            subprocess.run([grub_checker(), str(path)], check=True)

    def test_missing_console_tool_is_rejected_before_packaging(self):
        members = {'usr/sbin/e2fsck': (stat.S_IFREG | 0o755, b'elf')}
        with self.assertRaisesRegex(ValueError, 'requires setsid'):
            require_recovery_tools(members)
        members['usr/bin/setsid'] = (stat.S_IFLNK | 0o777, b'/bin/busybox')
        members['bin/busybox'] = (stat.S_IFREG | 0o755, b'elf')
        require_recovery_tools(members)

    def test_native_is_explicit_and_preserves_base_independence(self):
        native = compose('base', overrides=[ROOT / 'release/overrides/emmc-native.json'])
        self.assertEqual(native['bootContract'], 'emmc-file-store-v1')
        self.assertEqual(set(native['containers']), {'core'})
        self.assertEqual(compose('base')['bootContract'], 'ubuntu-file-store-v1')

    def test_recovery_has_no_support_filesystem_dependency(self):
        text = native_grub('11111111-1111-4111-8111-111111111111', '1' * 32, recovery_only=True)
        self.assertNotIn('search ', text)
        self.assertNotIn('load_env', text)
        self.assertIn('linux (memdisk)/recovery/kernel', text)
        self.assertIn('initrd (memdisk)/recovery/initramfs', text)

    def test_failure_reenters_embedded_menu_and_configs_parse(self):
        for recovery in (False, True):
            text = native_grub('11111111-1111-4111-8111-111111111111', '1' * 32,
                               emulated=True, recovery_only=recovery)
            self.assertNotIn('configfile ($root)', text)
            if not recovery:
                self.assertIn('configfile (memdisk)/boot/grub/grub.cfg', text)
                self.assertIn('set ventuno_recovery=1', text)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'grub.cfg'
                path.write_text(text)
                subprocess.run([grub_checker(), str(path)], check=True)

    def test_invalid_filesystem_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            native_grub('bad; reboot', '1' * 32)
