"""Resource budget for the 16 GB Ventuno: reserve the host before Kubernetes."""
import re
MIB = 1024 * 1024
HOST_RESERVE_MIB = 1024
K0S_RESERVE_MIB = 1024
EVICTION_MIB = 512
BOARD_MEMORY_KIB = 15651824


def memory_budget(memory_kib=BOARD_MEMORY_KIB):
    if not isinstance(memory_kib, int) or memory_kib < 4 * 1024 * 1024 - 512 * 1024:
        raise ValueError('This policy requires approximately 4 GiB or more usable memory')
    # Round down the container cap, keeping at least one GiB outside k0s.
    limit = (memory_kib // 1024 - HOST_RESERVE_MIB) * MIB
    outside_kib = memory_kib - limit // 1024
    return {'memory_total_kib': memory_kib, 'k0s_memory_max': limit,
            'k0s_memory_high': limit - 256 * MIB,
            'system_reserved_kib': outside_kib, 'kube_reserved_kib': K0S_RESERVE_MIB * 1024,
            'eviction_kib': EVICTION_MIB * 1024,
            'kubelet_eviction_kib': EVICTION_MIB * 1024,
            'pod_allocatable_kib': limit // 1024 - (K0S_RESERVE_MIB + EVICTION_MIB) * 1024}


def quantity_bytes(value):
    match = re.fullmatch(r'(\d+)(Ki|Mi|Gi)?', str(value))
    if not match: raise ValueError('Unsupported memory quantity: ' + str(value))
    return int(match[1]) * {None: 1, 'Ki': 1024, 'Mi': MIB, 'Gi': 1024 * MIB}[match[2]]


def validate_node_budget(node, config, status):
    capacity = quantity_bytes(node['status']['capacity']['memory'])
    allocatable = quantity_bytes(node['status']['allocatable']['memory'])
    kubelet = config['kubeletconfig']
    reserved = quantity_bytes(kubelet['kubeReserved']['memory'])
    host_reserved = quantity_bytes(kubelet['systemReserved']['memory'])
    eviction = quantity_bytes(kubelet['evictionHard']['memory.available'])
    limit = int(status['K0S_MEMORY_MAX'])
    assert allocatable == capacity - host_reserved - reserved - eviction, (capacity, allocatable, host_reserved, reserved, eviction)
    assert reserved == 1024 * MIB and host_reserved >= 1024 * MIB and eviction == 512 * MIB
    assert 'pods' in kubelet['enforceNodeAllocatable']
    assert allocatable <= limit - 1536 * MIB + MIB
    assert int(status['HOST_MEMORY_KIB']) * 1024 - limit >= 1024 * MIB
    return {'capacity_bytes': capacity, 'allocatable_bytes': allocatable, 'k0s_limit_bytes': limit,
            'kube_reserved_bytes': reserved, 'eviction_threshold_bytes': eviction,
            'host_reserved_bytes': host_reserved,
            'allocatable_cpu': node['status']['allocatable']['cpu']}
