"""Pinned KAS builds and credential-free component bundles."""
import gzip
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
from .model import ROOT, canonical, compose, digest, load, version
from .vendor import copy_selection

KAS_IMAGE = 'ghcr.io/siemens/kas/kas@sha256:22c70f90e21997c0b6743ad2d802cf1d942c28e974361c4733b8a026cb7ef809'


def run_build(profile, *, ci=False, detach=False):
    if profile not in ('base', 'k0s'): raise ValueError('Unknown build profile')
    build_directory = ('yocto-ci/' if ci else 'yocto/') + profile
    for name in ('downloads', 'sstate-cache', build_directory):
        (ROOT / 'artifacts' / name).mkdir(parents=True, exist_ok=True)
    configs = ['/work/kas/base.yml']
    if profile == 'k0s': configs.append('/work/kas/k0s.yml')
    if ci: configs.append('/work/kas/ci.yml')
    free = shutil.disk_usage(ROOT).free
    print(f'Build profile={profile}; free disk={free // 1024**3} GiB; CI={ci}', flush=True)
    if free < 8 * 1024 ** 3: raise RuntimeError('Less than 8 GiB free before the build')
    command = ['podman', 'run', '--detach' if detach else '--rm', '--name', 'ventuno-build-' + profile,
               '--userns=keep-id:uid=30000,gid=30000', '--security-opt', 'label=disable',
               '-v', str(ROOT) + ':/work', '-w', '/work', '-e', 'KAS_WORK_DIR=/work',
               '-e', 'KAS_BUILD_DIR=/work/artifacts/' + build_directory,
               KAS_IMAGE, 'build', ':'.join(configs)]
    if detach:
        subprocess.run(command, check=True)
        return
    start = time.monotonic()
    minimum = free
    process = subprocess.Popen(command)
    while process.poll() is None:
        minimum = min(minimum, shutil.disk_usage(ROOT).free)
        time.sleep(5)
    metrics = ROOT / 'artifacts/metrics'
    metrics.mkdir(exist_ok=True)
    (metrics / ('build-' + profile + '.json')).write_bytes(canonical({
        'profile': profile, 'ci': ci, 'initialFreeBytes': free, 'minimumFreeBytes': minimum,
        'elapsedSeconds': round(time.monotonic() - start), 'exitCode': process.returncode}))
    if process.returncode: raise RuntimeError('KAS build failed; see build log and disk metrics')


def source_info():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'], cwd=ROOT, text=True))
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT))
    repository = os.environ.get('GITHUB_REPOSITORY', load(ROOT / 'release/project.json')['repository'])
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository): raise ValueError('Invalid source repository')
    return {'commit': commit, 'epoch': epoch, 'dirty': dirty, 'repository': repository}


def stage_build(profile, output, *, ci=False):
    if profile not in ('base', 'k0s'): raise ValueError('Unknown profile')
    deploy = ROOT / ('artifacts/yocto-ci' if ci else 'artifacts/yocto') / profile / 'tmp/deploy/images/ventuno-q'
    output.mkdir(parents=True, exist_ok=False)
    images = ['ventuno-core-image'] + (['ventuno-k0s-image'] if profile == 'k0s' else [])
    names = [image + '-ventuno-q.' + suffix for image in images for suffix in ('squashfs', 'manifest', 'spdx.tar.zst')]
    names += ['ventuno-core-image-ventuno-q.core-release.json']
    if profile == 'base': names += ['pantavisor-initramfs-ventuno-q.cpio.gz', 'pantavisor-initramfs-ventuno-q.spdx.tar.zst']
    for name in names: shutil.copyfile(deploy / name, output / name)
    return output


def fetch_package(package, cache):
    path = cache / package['url'].rsplit('/', 1)[-1]
    if path.exists() and digest(path) == package['sha256']: return path
    partial = path.with_suffix(path.suffix + '.part')
    try:
        with urllib.request.urlopen(package['url'], timeout=120) as response, partial.open('wb') as target:
            shutil.copyfileobj(response, target)
        if digest(partial) != package['sha256']: raise ValueError('Vendor package checksum mismatch: ' + package['name'])
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def deterministic_tar(directory, destination, epoch):
    with destination.open('wb') as output:
        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
            process = subprocess.Popen(['tar', '--sort=name', '--format=posix',
                '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime',
                '--mtime=@' + str(epoch), '--owner=0', '--group=0', '--numeric-owner',
                '-C', str(directory), '-cf', '-', '.'], stdout=subprocess.PIPE)
            shutil.copyfileobj(process.stdout, compressed)
            process.stdout.close()
            if process.wait(): raise RuntimeError('Vendor archive creation failed')


def package_bsp(destination, initramfs, epoch):
    lock = load(ROOT / 'release/platform.lock.json')
    policy = load(ROOT / lock['selection'])
    cache = ROOT / 'artifacts/release-vendor'
    cache.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='release-vendor-') as temporary:
        work = Path(temporary)
        unpacked = work / 'root'
        unpacked.mkdir()
        for package in lock['packages']:
            archive = fetch_package(package, cache)
            members = subprocess.check_output(['ar', 't', str(archive)], text=True).splitlines()
            member, = [name for name in members if name == 'data.tar' or name.startswith('data.tar.')]
            data = work / member
            with data.open('wb') as stream:
                subprocess.run(['ar', 'p', str(archive), member], stdout=stream, check=True)
            subprocess.run(['tar', '-xf', str(data), '--no-same-owner', '-C', str(unpacked)], check=True)
            data.unlink()
        release = lock['kernelRelease']
        # Debian usrmerge is normally supplied by base-files. Package-only
        # extraction must also preserve candidates installed under usr/lib.
        if (unpacked / 'usr/lib/firmware').is_dir():
            shutil.copytree(unpacked / 'usr/lib/firmware', unpacked / 'lib/firmware', dirs_exist_ok=True, symlinks=True)
        if digest(unpacked / 'boot' / ('vmlinuz-' + release)) != lock['kernelSha256']:
            raise ValueError('Kernel differs from the qualified board kernel')
        if digest(unpacked / 'boot' / ('config-' + release)) != lock['kernelConfigSha256']:
            raise ValueError('Kernel configuration mismatch')
        subprocess.run(['depmod', '-b', str(unpacked), release], check=True)
        selected = work / 'selected'
        selection = copy_selection(unpacked, selected, 'lib', release, policy)
        for relative in ('boot', 'etc/modprobe.d', 'usr/lib/modprobe.d'):
            (selected / relative).mkdir(parents=True, exist_ok=True)
        notices = destination / 'licenses'
        notices.mkdir()
        for path in (unpacked / 'usr/share/doc').glob('*/copyright'):
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, notices / (path.parent.name + '.copyright'))
        for prefix in ('vmlinuz-', 'config-'):
            shutil.copyfile(unpacked / 'boot' / (prefix + release), selected / 'boot' / (prefix + release))
        subprocess.run(['depmod', '-b', str(selected), release], check=True)
        deterministic_tar(selected, destination / 'vendor-root.tar.gz', epoch)
        shutil.copyfile(selected / 'boot' / ('vmlinuz-' + release), destination / 'kernel.img')
    shutil.copyfile(initramfs, destination / 'initramfs-base.cpio.gz')
    (destination / 'selection.json').write_bytes(canonical(policy))
    (destination / 'selection-result.json').write_bytes(canonical(selection))
    (destination / 'platform.lock.json').write_bytes(canonical(lock))
    # This is an input to device provisioning, not an image to dd onto eMMC.
    from .cpio import newc_members
    boot_contracts = ['ubuntu-file-store-v1']
    names = {name for name, _, _ in newc_members(gzip.decompress(initramfs.read_bytes()))}
    if {'usr/sbin/ventuno-native-guard', 'usr/sbin/ventuno-native-bootctl'} <= names:
        boot_contracts.append('emmc-file-store-v1')
    (destination / 'bsp.json').write_bytes(canonical({
        'schema': 1, 'kind': 'bsp-components', 'kernel_release': release,
        'kernel_sha256': lock['kernelSha256'], 'kernel_config_sha256': lock['kernelConfigSha256'],
        'archive': 'vendor-root.tar.gz', 'sha256': digest(destination / 'vendor-root.tar.gz'),
        'deviceProvisioningRequired': True, 'bootContract': 'ubuntu-file-store-v1', 'bootContracts': boot_contracts}))


def package(profile, release_version, output, deploy_dir=None, *, ci=False):
    release_version = version(release_version)
    composition = compose(profile)
    source = source_info()
    deploy = deploy_dir or ROOT / ('artifacts/yocto-ci' if ci else 'artifacts/yocto') / profile / 'tmp/deploy/images/ventuno-q'
    output.mkdir(parents=True, exist_ok=False)
    components = {}
    core_name = composition['containers']['core']['artifact']
    for name, image in [(core_name, 'ventuno-core-image')] + ([('k0s', 'ventuno-k0s-image')] if profile == 'k0s' else []):
        directory = output / 'components' / name
        directory.mkdir(parents=True)
        shutil.copyfile(deploy / (image + '-ventuno-q.squashfs'), directory / 'rootfs.squashfs')
        shutil.copyfile(deploy / (image + '-ventuno-q.manifest'), directory / 'packages.manifest')
        shutil.copyfile(deploy / (image + '-ventuno-q.spdx.tar.zst'), directory / 'sbom.spdx.tar.zst')
        if name.startswith('core'):
            release = load(deploy / 'ventuno-core-image-ventuno-q.core-release.json')
            if bool(release.get('kubernetes_tools')) != (profile == 'k0s'):
                raise ValueError('Core image does not match the selected profile')
            (directory / 'core-release.json').write_bytes(canonical(release))
        metadata = {'schema': 1, 'kind': 'rootfs', 'name': name, 'architecture': 'arm64',
                    'runtimeABI': 'core-v1' if name.startswith('core') else 'k0s-v1',
                    'version': release_version, 'source': source,
                    'rootfsSha256': digest(directory / 'rootfs.squashfs')}
        (directory / 'component.json').write_bytes(canonical(metadata))
        components[name] = {'kind': 'rootfs', 'directory': 'components/' + name,
                            'rootfsSha256': metadata['rootfsSha256']}
    if profile == 'base':
        package_bsp(output / 'components/bsp', deploy / 'pantavisor-initramfs-ventuno-q.cpio.gz', source['epoch'])
        shutil.copyfile(deploy / 'pantavisor-initramfs-ventuno-q.spdx.tar.zst', output / 'components/bsp/sbom.spdx.tar.zst')
        components['bsp'] = {'kind': 'bsp', 'directory': 'components/bsp'}
    files = {path.relative_to(output).as_posix(): {'sha256': digest(path), 'size': path.stat().st_size}
             for path in sorted(output.rglob('*')) if path.is_file()}
    bundle = {'schema': 1, 'kind': 'release-components', 'version': release_version,
              'profile': profile, 'source': source, 'kasImage': KAS_IMAGE,
              'composition': composition, 'components': components, 'files': files}
    (output / 'bundle.json').write_bytes(canonical(bundle))
    return bundle


def verify_bundle(directory):
    bundle = load(directory / 'bundle.json')
    if bundle.get('schema') != 1 or bundle.get('kind') != 'release-components':
        raise ValueError('Not a publishable component bundle')
    version(bundle['version'])
    for name, component in bundle['components'].items():
        if not re.fullmatch(r'[a-z][a-z0-9-]*', name) or component['directory'] != 'components/' + name:
            raise ValueError('Invalid component directory')
        if component['kind'] not in ('bsp', 'rootfs'): raise ValueError('Unknown component kind')
    expected = set(bundle['files']) | {'bundle.json'}
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file() or path.is_symlink()}
    if actual != expected: raise ValueError('Unexpected or missing bundle files')
    for name, info in bundle['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe bundle path')
        source = directory / path
        if source.is_symlink() or source.stat().st_size != info['size'] or digest(source) != info['sha256']:
            raise ValueError('Bundle verification failed: ' + name)
    for component in bundle['components'].values():
        if component['kind'] == 'rootfs':
            if digest(directory / component['directory'] / 'rootfs.squashfs') != component['rootfsSha256']:
                raise ValueError('Component rootfs digest does not match its descriptor')
    return bundle
