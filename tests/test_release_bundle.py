import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.pvbuild.build import verify_bundle
from tools.pvbuild.model import canonical, digest
from tools.pvbuild.oci import check_destination


class BundleTests(unittest.TestCase):
    def test_content_verification_rejects_changes_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'payload').write_bytes(b'public payload')
            bundle = {'schema': 1, 'kind': 'release-components', 'version': '0.1.0', 'components': {},
                      'files': {'payload': {'sha256': digest(directory / 'payload'), 'size': 14}}}
            (directory / 'bundle.json').write_bytes(canonical(bundle))
            verify_bundle(directory)
            (directory / 'private-key').write_text('must never be included')
            with self.assertRaises(ValueError): verify_bundle(directory)
            (directory / 'private-key').unlink()
            (directory / 'payload').write_bytes(b'changed bytes!')
            with self.assertRaises(ValueError): verify_bundle(directory)

    def test_private_device_state_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'bundle.json').write_bytes(canonical({'schema': 1, 'kind': 'private-device-state'}))
            with self.assertRaises(ValueError): verify_bundle(directory)

    def test_existing_tag_is_immutable(self):
        with patch('tools.pvbuild.oci.remote_digest', return_value='sha256:' + 'a' * 64):
            self.assertTrue(check_destination('ghcr.io/example/core:0.1.0', 'sha256:' + 'a' * 64))
            with self.assertRaises(ValueError): check_destination('ghcr.io/example/core:0.1.0', 'sha256:' + 'b' * 64)
        with patch('tools.pvbuild.oci.remote_digest', return_value=None):
            self.assertFalse(check_destination('ghcr.io/example/core:0.1.0', 'sha256:' + 'a' * 64))
