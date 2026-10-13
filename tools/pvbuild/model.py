"""Versioned, deterministic composition of Pantavisor system layers."""
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
DIGEST_RE = r'sha256:[0-9a-f]{64}'
REF_RE = r'ghcr\.io/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}'


def load(path):
    return json.loads(Path(path).read_text())


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(VERSION_RE, value):
        raise ValueError('Expected canonical MAJOR.MINOR.PATCH without v or leading zeros')
    return value


def merge(base, patch):
    """Maps merge recursively, arrays/scalars replace, null deletes a key."""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def integer(value, minimum, maximum, field):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{field} must be an integer in {minimum}..{maximum}')


def validate(composition):
    if set(composition) - {'schema', 'platform', 'architecture', 'bootContract', 'layers', 'bsp', 'containers',
                            'profile', 'version', 'revision', 'artifacts', 'compositionDigest'}:
        raise ValueError('Unknown composition fields')
    if composition.get('schema') != 1 or composition.get('platform') != 'ventuno-q' or composition.get('architecture') != 'arm64':
        raise ValueError('Unsupported composition schema/platform/architecture')
    if composition.get('bootContract') not in ('ubuntu-file-store-v1', 'emmc-file-store-v1'):
        raise ValueError('Native eMMC provisioning is not implemented/qualified yet')
    if not re.fullmatch(r'[a-z][a-z0-9-]*', composition.get('bsp', '')): raise ValueError('Invalid BSP artifact key')
    containers = composition.get('containers', {})
    if not isinstance(containers, dict) or 'core' not in containers:
        raise ValueError('The base core container cannot be removed')
    for name, container in containers.items():
        if name not in ('core', 'k0s'):
            raise ValueError(f'No runtime adapter for container {name!r}')
        if not re.fullmatch(r'[a-z][a-z0-9-]*', container.get('artifact', '')):
            raise ValueError('Artifact keys must be simple lowercase names')
    core = containers['core']
    if set(core) != {'artifact', 'memoryMiB', 'cpuWeight', 'settings'} or set(core['settings']) != {'sshPort', 'ntpServers'}:
        raise ValueError('Unknown/missing core settings; device credentials belong in the private device configuration')
    integer(core.get('memoryMiB'), 128, 4096, 'core.memoryMiB')
    integer(core.get('cpuWeight'), 1, 10000, 'core.cpuWeight')
    integer(core['settings'].get('sshPort'), 1024, 65535, 'core.sshPort')
    peers = core['settings'].get('ntpServers')
    if not isinstance(peers, list) or not peers or any(not re.fullmatch(r'[a-zA-Z0-9.:-]+', p) for p in peers):
        raise ValueError('Invalid NTP servers')
    if 'k0s' in containers:
        k0s = containers['k0s']
        if set(k0s) != {'artifact', 'hostReserveMiB', 'kubeReserveMiB', 'evictionMiB', 'settings'}:
            raise ValueError('Unknown/missing k0s settings')
        integer(k0s.get('hostReserveMiB'), core['memoryMiB'] + 256, 8192, 'k0s.hostReserveMiB')
        integer(k0s.get('kubeReserveMiB'), 512, 8192, 'k0s.kubeReserveMiB')
        integer(k0s.get('evictionMiB'), 128, 4096, 'k0s.evictionMiB')
        settings = k0s['settings']
        if set(settings) != {'podCIDR', 'serviceCIDR', 'maxPods', 'disabledComponents'}:
            raise ValueError('Unknown/missing k0s runtime settings')
        integer(settings.get('maxPods'), 1, 110, 'k0s.maxPods')
        pod = ipaddress.IPv4Network(settings['podCIDR'])
        service = ipaddress.IPv4Network(settings['serviceCIDR'])
        if pod.overlaps(service): raise ValueError('Pod and service networks overlap')
        if any(not re.fullmatch(r'[a-z][a-z0-9-]*', item) for item in settings['disabledComponents']):
            raise ValueError('Invalid disabled k0s component')
    return composition


def compose(profile='k0s', *, layers=(), overrides=(), root=ROOT):
    if not re.fullmatch(r'[a-z][a-z0-9-]*', profile): raise ValueError('Invalid profile name')
    result = load(root / 'release/base.json')
    definition = load(root / 'release/profiles' / (profile + '.json'))
    if definition.get('schema') != 1: raise ValueError('Unsupported profile schema')
    for path in [root / 'release/layers' / (name + '.json') for name in definition['layers']] + list(map(Path, layers)):
        layer = load(path)
        if layer.get('schema') != 1 or not isinstance(layer.get('patch'), dict):
            raise ValueError('Unsupported layer schema')
        name = layer.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', name) or name in result['layers']:
            raise ValueError('Invalid/duplicate layer name')
        if not set(layer.get('requires', [])) <= set(result['layers']):
            raise ValueError(f'Unmet requirements for layer {name}')
        if set(layer['patch']) - {'containers'}:
            raise ValueError('A layer may override containers, not platform or boot identity')
        result = merge(result, layer['patch'])
        result['layers'].append(name)
    for patch in [definition.get('overrides', {})] + [load(path) for path in overrides]:
        if set(patch) - {'containers', 'bootContract'}: raise ValueError('Overrides are scoped to containers and bootContract')
        result = merge(result, patch)
    result['profile'] = definition['name']
    return validate(result)


def lock_composition(composition, artifacts, release_version):
    """Resolve every component to immutable OCI image and rootfs descriptors."""
    result = copy.deepcopy(composition)
    result['version'] = version(release_version)
    result['revision'] = 'locals/' + release_version
    required = {composition['bsp']} | {item['artifact'] for item in composition['containers'].values()}
    resolved = {}
    for name in sorted(required):
        item = artifacts.get(name)
        if not isinstance(item, dict) or not re.fullmatch(REF_RE, item.get('ref', '')):
            raise ValueError(f'Missing digest-pinned GHCR artifact: {name}')
        if set(item) - {'ref', 'image', 'rootfsSha256'}: raise ValueError('Unexpected artifact descriptor fields')
        if '..' in item['ref'].split('/'): raise ValueError('Invalid registry reference')
        if name != composition['bsp'] and not re.fullmatch(REF_RE, item.get('image', '')):
            raise ValueError(f'Missing digest-pinned OCI image: {name}')
        if name != composition['bsp'] and not re.fullmatch(r'[0-9a-f]{64}', item.get('rootfsSha256', '')):
            raise ValueError('Missing rootfs checksum')
        resolved[name] = item
    result['artifacts'] = resolved
    result['compositionDigest'] = 'sha256:' + hashlib.sha256(canonical(result)).hexdigest()
    return result
