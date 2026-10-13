from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from resource_policy import memory_budget, MIB


class ResourcePolicyTests(unittest.TestCase):
    def test_board_keeps_host_and_control_plane_headroom(self):
        policy = memory_budget()
        self.assertGreaterEqual(policy['memory_total_kib'] * 1024 - policy['k0s_memory_max'], 1024 * MIB)
        self.assertEqual(policy['k0s_memory_max'] - policy['pod_allocatable_kib'] * 1024, 1536 * MIB)
        self.assertEqual(policy['pod_allocatable_kib'], policy['memory_total_kib'] -
                         policy['system_reserved_kib'] - policy['kube_reserved_kib'] - policy['kubelet_eviction_kib'])
        self.assertGreater(policy['pod_allocatable_kib'], 12 * 1024 * 1024)
        self.assertLess(policy['k0s_memory_high'], policy['k0s_memory_max'])

    def test_vm_budget_is_bounded_and_small_targets_are_rejected(self):
        policy = memory_budget(3990200)
        self.assertLess(policy['k0s_memory_max'], 3 * 1024 * MIB)
        self.assertGreater(policy['pod_allocatable_kib'], 1024 * 1024)
        with self.assertRaises(ValueError): memory_budget(2 * 1024 * 1024)
