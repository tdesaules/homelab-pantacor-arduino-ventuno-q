"""Fetch immutable release compositions and component artifacts from GHCR."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
from .build import source_info, verify_bundle
from .model import ROOT, REF_RE, canonical, digest, load, lock_composition, validate, version
from .oci import oras_command


def fetch(output, *, reference=None, profile='k0s', composition_path=None):
    if bool(reference) == bool(composition_path): raise ValueError('Choose a catalogue reference or a composition lock')
    source = source_info()
    if reference:
        if not re.fullmatch(REF_RE, reference): raise ValueError('A digest-pinned GHCR reference is required')
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='catalogue-') as temporary:
            subprocess.run(oras_command('pull', reference, '--output', temporary), check=True)
            catalogue = load(Path(temporary) / 'release.json')
            if catalogue.get('schema') != 1 or catalogue.get('kind') != 'release-catalogue':
                raise ValueError('Unsupported release catalogue')
            composition = catalogue['profiles'][profile]
            source = catalogue['source']
    else:
        composition = load(composition_path)
    validate(composition)
    expected = composition['compositionDigest']
    plain = {key: value for key, value in composition.items() if key != 'compositionDigest'}
    if expected != 'sha256:' + hashlib.sha256(canonical(plain)).hexdigest():
        raise ValueError('Composition lock digest mismatch')
    # Revalidate references and rootfs checksums, including external layer inputs.
    base = {key: value for key, value in composition.items() if key not in ('version', 'revision', 'artifacts', 'compositionDigest')}
    resolved = lock_composition(base, composition['artifacts'], composition['version'])
    if resolved['artifacts'] != composition['artifacts']: raise ValueError('Unexpected unused artifact entries')
    output.mkdir(parents=True, exist_ok=False)
    components = {}
    for name, item in composition['artifacts'].items():
        destination = output / 'components' / name
        destination.mkdir(parents=True)
        subprocess.run(oras_command('pull', item['ref'], '--output', str(destination)), check=True)
        if any(path.is_symlink() for path in destination.rglob('*')):
            raise ValueError('Component artifacts must contain plain files, not symlinks')
        if name == composition['bsp']:
            bsp = load(destination / 'bsp.json')
            if composition['bootContract'] not in bsp.get('bootContracts', [bsp['bootContract']]):
                raise ValueError('BSP boot contract mismatch')
            components[name] = {'kind': 'bsp', 'directory': 'components/' + name}
        else:
            metadata = load(destination / 'component.json')
            expected_abi = 'core-v1' if composition['containers']['core']['artifact'] == name else 'k0s-v1'
            if metadata.get('architecture') != 'arm64' or metadata.get('runtimeABI') != expected_abi:
                raise ValueError('Component does not implement the selected runtime ABI')
            if digest(destination / 'rootfs.squashfs') != item['rootfsSha256']:
                raise ValueError('Fetched rootfs checksum mismatch')
            components[name] = {'kind': 'rootfs', 'directory': 'components/' + name, 'rootfsSha256': item['rootfsSha256']}
    files = {path.relative_to(output).as_posix(): {'sha256': digest(path), 'size': path.stat().st_size}
             for path in sorted(output.rglob('*')) if path.is_file()}
    bundle = {'schema': 1, 'kind': 'release-components', 'version': version(composition['version']),
              'profile': profile, 'source': source, 'composition': base, 'components': components,
              'files': files, 'upstreamCompositionDigest': expected}
    (output / 'bundle.json').write_bytes(canonical(bundle))
    verify_bundle(output)
    return bundle
