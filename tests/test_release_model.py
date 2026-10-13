import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.pvbuild.model import ROOT, compose, lock_composition, merge, version


class CompositionTests(unittest.TestCase):
    def test_base_is_independent_and_k0s_is_an_added_layer(self):
        base = compose('base')
        cluster = compose('k0s')
        self.assertEqual(set(base['containers']), {'core'})
        self.assertEqual(base['containers']['core']['artifact'], 'core')
        self.assertEqual(set(cluster['containers']), {'core', 'k0s'})
        self.assertEqual(cluster['containers']['core']['artifact'], 'core-kubernetes')
        self.assertEqual(cluster['layers'], ['base', 'k0s'])

    def test_overrides_are_explicit_and_do_not_mutate_the_base(self):
        before = compose('k0s')
        result = compose('k0s', overrides=[ROOT / 'release/overrides/k0s-example.json'])
        self.assertEqual(result['containers']['k0s']['settings']['maxPods'], 60)
        self.assertEqual(compose('k0s'), before)
        value = {'a': {'b': [1, 2], 'c': 3}}
        original = copy.deepcopy(value)
        self.assertEqual(merge(value, {'a': {'b': [4], 'c': None}}), {'a': {'b': [4]}})
        self.assertEqual(value, original)

    def test_rejects_missing_core_and_device_credentials_in_release(self):
        for patch in ({'containers': {'core': None}},
                      {'containers': {'core': {'settings': {'privateKey': 'secret'}}}},
                      {'bootContract': 'native-emmc-v1'},
                      {'containers': {'k0s': {'settings': {'podCIDR': '10.96.0.0/16'}}}}):
            with self.subTest(patch=patch), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'override.json'
                path.write_text(json.dumps(patch))
                with self.assertRaises((ValueError, KeyError)): compose('k0s', overrides=[path])

    def test_external_layer_can_replace_an_artifact_with_a_pinned_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'layer.json'
            path.write_text(json.dumps({'schema': 1, 'name': 'custom-k0s', 'requires': ['k0s'],
                                       'patch': {'containers': {'k0s': {'artifact': 'custom-k0s'}}}}))
            composition = compose('k0s', layers=[path])
            artifacts = {name: {'ref': 'ghcr.io/example/os/' + name + '@sha256:' + 'a' * 64}
                         for name in ('bsp', 'core-kubernetes', 'custom-k0s')}
            for name in ('core-kubernetes', 'custom-k0s'):
                artifacts[name].update(image='ghcr.io/example/os/' + name + '@sha256:' + 'b' * 64, rootfsSha256='c' * 64)
            result = lock_composition(composition, artifacts, '0.1.0')
            self.assertEqual(result['revision'], 'locals/0.1.0')
            self.assertIn('custom-k0s', result['artifacts'])
            self.assertEqual(result, lock_composition(composition, artifacts, '0.1.0'))
            artifacts['custom-k0s']['image'] = 'ghcr.io/example/os/custom-k0s:latest'
            with self.assertRaises(ValueError): lock_composition(composition, artifacts, '0.1.0')
            with self.assertRaises(ValueError): compose('base', layers=[path])

    def test_release_version_is_canonical(self):
        self.assertEqual(version('0.1.0'), '0.1.0')
        for invalid in ('v0.1.0', '0.01.0', '0.1', '0.1.0;reboot', '../0.1.0'):
            with self.assertRaises(ValueError): version(invalid)
