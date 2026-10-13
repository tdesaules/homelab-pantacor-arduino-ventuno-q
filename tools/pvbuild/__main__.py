"""Usage: python3 -m tools.pvbuild --help."""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from .model import ROOT, canonical, compose, load, lock_composition, version


def main():
    parser = argparse.ArgumentParser(description='Build and compose Pantavisor system releases; no board access')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('compose', help='Merge a base, optional layers and overrides')
    p.add_argument('--profile', choices=('base', 'k0s'), default='k0s')
    p.add_argument('--layer', type=Path, action='append', default=[])
    p.add_argument('--override', type=Path, action='append', default=[])
    p.add_argument('--artifacts', type=Path, help='Digest-pinned artifact map for a deployable composition lock')
    p.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    p.add_argument('--output', type=Path)
    p = commands.add_parser('build', help='Run pinned KAS/Yocto in Podman')
    p.add_argument('--profile', choices=('base', 'k0s'), required=True)
    p.add_argument('--ci', action='store_true')
    p.add_argument('--detach', action='store_true')
    p = commands.add_parser('package', help='Create a credential-free component bundle')
    p.add_argument('--profile', choices=('base', 'k0s'), required=True)
    p.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    p.add_argument('--deploy-dir', type=Path)
    p.add_argument('--ci', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('stage-build', help='Preserve only deploy outputs before freeing CI build space')
    p.add_argument('--profile', choices=('base', 'k0s'), required=True)
    p.add_argument('--ci', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('verify', help='Check a component bundle and reject extra files')
    p.add_argument('bundle', type=Path)
    p = commands.add_parser('oci', help='Convert a verified SquashFS component into a standard OCI image layout')
    p.add_argument('--component', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('_export-tar', help=argparse.SUPPRESS)
    p.add_argument('--rootfs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--epoch', type=int, required=True)
    p = commands.add_parser('upload-build', help='Transfer verified build outputs through GHCR')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--reference', required=True)
    p = commands.add_parser('download-build', help='Download build outputs by digest and verify every file')
    p.add_argument('--reference', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('publish', help='Publish OCI images, rootfs/BSP artifacts and the release catalogue')
    p.add_argument('--bundle', type=Path, action='append', required=True)
    p.add_argument('--registry', required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('smoke', help='Check component executables and absence of baked-in credentials')
    p.add_argument('--bundle', type=Path, required=True)
    p = commands.add_parser('render', help='Render a private device state; never formats or installs a device')
    p.add_argument('--bundle', type=Path, action='append', required=True)
    p.add_argument('--profile', choices=('base', 'k0s'), default='k0s')
    p.add_argument('--device', type=Path, required=True)
    p.add_argument('--layer', type=Path, action='append', default=[])
    p.add_argument('--override', type=Path, action='append', default=[])
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('fetch', help='Fetch a release catalogue or custom composition lock by digest')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--reference')
    group.add_argument('--composition', type=Path)
    p.add_argument('--profile', choices=('base', 'k0s'), default='k0s')
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('integration', help='Isolated full QEMU test in a clean ARM64 CI workspace')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--k0s', type=Path)
    p = commands.add_parser('native-package', help='Prepare a private native eMMC tree and independent EFI rescue; no device writes')
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--system-uuid', required=True)
    p.add_argument('--esp-uuid', help='Also generate the factory-loader ESP dispatcher')
    p.add_argument('--grub-modules', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--emulated', action='store_true')
    p.add_argument('--store-mib', type=int, default=4096)
    p = commands.add_parser('native-test', help='Qualify a native base package in isolated UEFI/QEMU fixtures')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--ssh-key', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scenario', action='append', help='Run only selected native-test scenarios')
    commands.add_parser('check', help='Run fast tests, syntax and documentation-link checks')
    p = commands.add_parser('check-version', help='Validate the intended release version and optional Git tag')
    p.add_argument('--tag')
    args = parser.parse_args()
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    if args.command == 'compose':
        result = compose(args.profile, layers=args.layer, overrides=args.override)
        if args.artifacts: result = lock_composition(result, load(args.artifacts), args.version)
        data = canonical(result)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
        else: sys.stdout.buffer.write(data)
    elif args.command == 'build':
        from .build import run_build
        run_build(args.profile, ci=args.ci, detach=args.detach)
    elif args.command == 'package':
        from .build import package
        package(args.profile, args.version, args.output, args.deploy_dir, ci=args.ci)
        print(args.output / 'bundle.json')
    elif args.command == 'stage-build':
        from .build import stage_build
        print(stage_build(args.profile, args.output, ci=args.ci))
    elif args.command == 'verify':
        from .build import verify_bundle
        bundle = verify_bundle(args.bundle)
        print('PASS:', bundle['profile'], bundle['version'])
    elif args.command == 'oci':
        from .oci import image_layout
        print(image_layout(args.component, args.output))
    elif args.command == '_export-tar':
        from .oci import export_tar
        export_tar(args.rootfs, args.output, args.epoch)
    elif args.command == 'upload-build':
        from .build import verify_bundle
        from .oci import push_artifact
        bundle = verify_bundle(args.bundle)
        if bundle['source']['dirty']: raise ValueError('Cannot publish a build from an uncommitted source tree')
        if not re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+:ci-[0-9]+-[0-9]+', args.reference):
            raise ValueError('Build transfers require a GHCR ci-<run>-<attempt> reference')
        created = datetime.datetime.fromtimestamp(bundle['source']['epoch'], datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        print(push_artifact(args.bundle, args.reference, 'application/vnd.ventuno.build.v1', created=created,
                            files=sorted(bundle['files']) + ['bundle.json'],
                            source='https://github.com/' + bundle['source']['repository']))
    elif args.command == 'download-build':
        from .build import verify_bundle
        from .oci import oras_command
        if not re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}', args.reference):
            raise ValueError('Download requires a digest-pinned GHCR reference')
        args.output.mkdir(parents=True, exist_ok=False)
        subprocess.run(oras_command('pull', args.reference, '--output', str(args.output)), check=True)
        verify_bundle(args.output)
    elif args.command == 'publish':
        from .oci import publish
        print(publish(args.bundle, args.registry, args.tag, args.output))
    elif args.command == 'smoke':
        from .checks import smoke
        smoke(args.bundle)
    elif args.command == 'render':
        from .render import render
        print(render(args.bundle, args.profile, args.device, args.output, overrides=args.override, layers=args.layer))
    elif args.command == 'fetch':
        from .fetch import fetch
        fetch(args.output, reference=args.reference, profile=args.profile, composition_path=args.composition)
        print(args.output / 'bundle.json')
    elif args.command == 'integration':
        from .integration import integration
        integration(args.base, args.k0s)
    elif args.command == 'native-package':
        from .native import prepare
        print(prepare(args.state, args.system_uuid, args.grub_modules, args.output,
                      emulated=args.emulated, size_mib=args.store_mib, esp_uuid=args.esp_uuid))
    elif args.command == 'native-test':
        from .native_test import SCENARIOS, qualify
        qualify(args.package, args.ssh_key, load(args.state / 'device-state.json')['sshHostPublicKey'], args.output,
                scenarios=args.scenario or SCENARIOS)
    elif args.command == 'check':
        from .checks import check
        check()
    elif args.command == 'check-version':
        value = version((ROOT / 'VERSION').read_text().strip())
        if args.tag is not None and args.tag != 'v' + value: raise ValueError('Git tag and VERSION differ')
        print(value)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, KeyError, FileNotFoundError) as error:
        raise SystemExit(str(error)) from error
