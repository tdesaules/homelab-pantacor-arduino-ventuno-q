"""OCI image layouts and GHCR publication with immutable-tag checks."""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from .build import verify_bundle
from .model import ROOT, canonical, digest, lock_composition, load, version

IMAGE_MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
IMAGE_CONFIG = 'application/vnd.oci.image.config.v1+json'
IMAGE_LAYER = 'application/vnd.oci.image.layer.v1.tar+gzip'


def oras_command(*args):
    command = ['oras', *args]
    if os.environ.get('REGISTRY_AUTH_FILE'):
        command += ['--registry-config', os.environ['REGISTRY_AUTH_FILE']]
    return command


def export_tar(rootfs, output, epoch):
    """Run inside podman's user namespace so numeric owners are preserved."""
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='rootfs-') as temporary:
        root = Path(temporary) / 'root'
        subprocess.run(['unsquashfs', '-no-progress', '-d', str(root), str(rootfs)], check=True, stdout=subprocess.DEVNULL)
        forbidden = [root / 'home/root/.ssh/authorized_keys', root / 'home/root/.kube/config']
        forbidden += list((root / 'etc/dropbear').glob('*host_key')) if (root / 'etc/dropbear').exists() else []
        for path in forbidden:
            if not path.is_symlink() and path.is_file() and path.stat().st_size:
                raise ValueError('Device credentials must not be published: ' + str(path.relative_to(root)))
        if (root / 'var/lib/k0s/pki').exists(): raise ValueError('Cluster PKI found in rootfs')
        with output.open('wb') as stream:
            subprocess.run(['tar', '--sort=name', '--format=posix', '--numeric-owner', '--xattrs',
                '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime',
                '--mtime=@' + str(epoch), '-C', str(root), '-cf', '-', '.'], stdout=stream, check=True)


def image_layout(component, output):
    metadata = load(component / 'component.json')
    if digest(component / 'rootfs.squashfs') != metadata['rootfsSha256']:
        raise ValueError('Rootfs digest mismatch')
    output.mkdir(parents=True, exist_ok=False)
    blobs = output / 'blobs/sha256'
    blobs.mkdir(parents=True)
    epoch = metadata['source']['epoch']
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='oci-layer-') as temporary:
        temporary = Path(temporary)
        tar = temporary / 'rootfs.tar'
        command = [sys.executable, '-m', 'tools.pvbuild', '_export-tar', '--rootfs', str((component / 'rootfs.squashfs').resolve()),
                   '--output', str(tar.resolve()), '--epoch', str(epoch)]
        subprocess.run(command if os.geteuid() == 0 else ['podman', 'unshare', *command], cwd=ROOT, check=True)
        diff_id = 'sha256:' + digest(tar)
        layer = temporary / 'rootfs.tar.gz'
        with tar.open('rb') as source, layer.open('wb') as stream:
            with gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        layer_sha = digest(layer)
        layer_size = layer.stat().st_size
        shutil.copyfile(layer, blobs / layer_sha)
    created = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
    core = metadata['name'].startswith('core')
    entrypoint = ['/usr/sbin/init.lxc.static', '--name', 'core' if core else 'k0s', '--',
                  '/usr/libexec/ventuno/core-init' if core else '/usr/libexec/ventuno/k0s-init']
    # These are system containers: DHCP/NTP and nested containerd require root.
    config = {'created': created, 'architecture': 'arm64', 'os': 'linux',
              'config': {'User': '0:0', 'Entrypoint': entrypoint,
                         'Env': ['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'],
                         'Labels': {'org.opencontainers.image.title': metadata['name'],
                                    'org.opencontainers.image.version': metadata['version'],
                                    'org.opencontainers.image.source': 'https://github.com/' + metadata['source']['repository'],
                                    'org.opencontainers.image.revision': metadata['source']['commit']}},
              'rootfs': {'type': 'layers', 'diff_ids': [diff_id]},
              'history': [{'created': created, 'created_by': 'pvbuild: verified Yocto rootfs'}]}
    config_bytes = canonical(config)
    config_sha = hashlib.sha256(config_bytes).hexdigest()
    (blobs / config_sha).write_bytes(config_bytes)
    manifest = {'schemaVersion': 2, 'mediaType': IMAGE_MANIFEST,
                'config': {'mediaType': IMAGE_CONFIG, 'digest': 'sha256:' + config_sha, 'size': len(config_bytes)},
                'layers': [{'mediaType': IMAGE_LAYER, 'digest': 'sha256:' + layer_sha, 'size': layer_size}]}
    encoded = canonical(manifest)
    manifest_sha = hashlib.sha256(encoded).hexdigest()
    (blobs / manifest_sha).write_bytes(encoded)
    (output / 'oci-layout').write_bytes(canonical({'imageLayoutVersion': '1.0.0'}))
    (output / 'index.json').write_bytes(canonical({'schemaVersion': 2, 'manifests': [{
        'mediaType': IMAGE_MANIFEST, 'digest': 'sha256:' + manifest_sha, 'size': len(encoded),
        'platform': {'architecture': 'arm64', 'os': 'linux'},
        'annotations': {'org.opencontainers.image.ref.name': 'image'}}]}))
    return 'sha256:' + manifest_sha


def remote_digest(reference):
    result = subprocess.run(oras_command('manifest', 'fetch', '--descriptor', reference), capture_output=True, text=True)
    if result.returncode == 0: return json.loads(result.stdout)['digest']
    if re.search(r'manifest unknown|manifest_unknown|404 not found|: not found\s*$', result.stderr, re.I): return None
    raise RuntimeError(result.stderr.strip() or 'Could not check registry reference')


def check_destination(reference, expected):
    existing = remote_digest(reference)
    if existing is not None and existing != expected:
        raise ValueError('Refusing to replace an existing tag with different content: ' + reference)
    return existing == expected


def push_artifact(directory, reference, artifact_type, *, created, files=None, source=None):
    paths = files or sorted(path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file())
    with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='oras-') as temporary:
        layout = str(Path(temporary) / 'layout') + ':artifact'
        command = ['oras', 'push', '--oci-layout', layout, '--artifact-type', artifact_type,
                   '--annotation', 'org.opencontainers.image.created=' + created, '--format', 'json']
        if source: command += ['--annotation', 'org.opencontainers.image.source=' + source]
        for name in paths:
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or (directory / path).is_symlink():
                raise ValueError('Unsafe artifact filename')
            mime = 'application/json' if path.suffix == '.json' else 'application/octet-stream'
            command.append(name + ':' + mime)
        result = subprocess.check_output(command, cwd=directory, text=True)
        expected = json.loads(result)['digest']
        if not check_destination(reference, expected):
            subprocess.run(oras_command('cp', '--from-oci-layout', layout, reference), check=True)
        if remote_digest(reference) != expected: raise ValueError('Registry digest differs after publication')
        return reference.rsplit(':', 1)[0] + '@' + expected


def publish(bundles, registry, tag, output):
    if not re.fullmatch(r'ghcr\.io/[a-z0-9][a-z0-9._/-]*', registry) or '..' in registry.split('/'):
        raise ValueError('Expected a lowercase GHCR namespace')
    loaded = [(directory, verify_bundle(directory)) for directory in bundles]
    if {bundle['profile'] for _, bundle in loaded} != {'base', 'k0s'} or len(loaded) != 2:
        raise ValueError('Publication requires exactly the base and k0s bundles')
    versions = {bundle['version'] for _, bundle in loaded}
    commits = {bundle['source']['commit'] for _, bundle in loaded}
    if len(versions) != 1 or len(commits) != 1 or any(bundle['source']['dirty'] for _, bundle in loaded):
        raise ValueError('Publication requires clean, matching source commits and versions')
    release_version, = versions
    if tag != release_version and not re.fullmatch(r'build-[0-9a-f]{40}', tag):
        raise ValueError('Tag must be the release version or build-<commit>')
    commit, = commits
    if tag.startswith('build-') and tag != 'build-' + commit: raise ValueError('Candidate tag/source mismatch')
    if tag == release_version:
        tagged = subprocess.check_output(['git', 'rev-parse', 'v' + version(tag) + '^{commit}'], cwd=ROOT, text=True).strip()
        if tagged != commit: raise ValueError('Git tag does not identify the built source commit')
    created = datetime.datetime.fromtimestamp(loaded[0][1]['source']['epoch'], datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
    source_url = 'https://github.com/' + loaded[0][1]['source']['repository']
    resolved = {}
    for directory, bundle in loaded:
        for name, component in bundle['components'].items():
            component_dir = directory / component['directory']
            if name in resolved: continue
            if component['kind'] == 'rootfs':
                with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='publish-image-') as temporary:
                    layout = Path(temporary) / 'image'
                    expected = image_layout(component_dir, layout)
                    reference = registry + '/' + name + ':' + tag
                    if not check_destination(reference, expected):
                        command = ['skopeo', 'copy', '--preserve-digests']
                        if os.environ.get('REGISTRY_AUTH_FILE'): command += ['--authfile', os.environ['REGISTRY_AUTH_FILE']]
                        command += ['oci:' + str(layout) + ':image', 'docker://' + reference]
                        subprocess.run(command, check=True)
                    if remote_digest(reference) != expected: raise ValueError('Published image digest mismatch')
                    image = registry + '/' + name + '@' + expected
                ref = push_artifact(component_dir, registry + '/' + name + '-rootfs:' + tag,
                                    'application/vnd.ventuno.rootfs.v1', created=created, source=source_url)
                resolved[name] = {'ref': ref, 'image': image, 'rootfsSha256': component['rootfsSha256']}
            else:
                ref = push_artifact(component_dir, registry + '/bsp:' + tag,
                                    'application/vnd.ventuno.bsp.v1', created=created, source=source_url)
                resolved[name] = {'ref': ref}
    profiles = {bundle['profile']: lock_composition(bundle['composition'], resolved, release_version) for _, bundle in loaded}
    if set(profiles) != {'base', 'k0s'}: raise ValueError('The release catalogue requires base and k0s profiles')
    output.mkdir(parents=True, exist_ok=False)
    catalogue = {'schema': 1, 'kind': 'release-catalogue', 'version': release_version,
                 'sourceCommit': commit, 'source': loaded[0][1]['source'], 'profiles': profiles}
    (output / 'release.json').write_bytes(canonical(catalogue))
    reference = push_artifact(output, registry + '/release:' + tag, 'application/vnd.ventuno.release.v1', created=created, source=source_url)
    (output / 'receipt.json').write_bytes(canonical({'reference': reference, 'version': release_version, 'tag': tag}))
    return reference
