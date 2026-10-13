"""Fast CI checks and ARM64 userspace smoke tests."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from .build import verify_bundle
from .model import ROOT, compose


def documentation_links():
    files = [ROOT / 'README.md'] + list((ROOT / 'docs').rglob('*.md')) + list((ROOT / 'release').rglob('*.md'))
    errors = []
    for path in files:
        if path.name.endswith('.local.md'): continue
        for target in re.findall(r'\]\(([^\s)]+)', path.read_text()):
            if target.startswith(('http:', 'https:', '#', 'mailto:')): continue
            target = target.split('#', 1)[0]
            if target and not (path.parent / target).exists(): errors.append(f'{path.relative_to(ROOT)}: {target}')
    if errors: raise ValueError('Broken documentation links:\n' + '\n'.join(errors))


def check():
    compose('base'); compose('k0s')
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'compileall', '-q', 'tools', 'lab', 'tests', 'examples/hello-api'], cwd=ROOT, check=True)
    for path in (ROOT / 'lab').glob('*.sh'):
        subprocess.run(['bash', '-n', str(path)], check=True)
    documentation_links()
    print('PASS: compositions, tests, syntax and documentation links')


def smoke(directory):
    bundle = verify_bundle(directory)
    for name, item in bundle['components'].items():
        if item['kind'] != 'rootfs': continue
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='smoke-') as temporary:
            temporary = Path(temporary)
            root = temporary / 'root'
            subprocess.run(['unsquashfs', '-no-progress', '-d', str(root), str(directory / item['directory'] / 'rootfs.squashfs')],
                           stdout=subprocess.DEVNULL, check=True)
            for secret in ('home/root/.ssh/authorized_keys', 'etc/dropbear/dropbear_ed25519_host_key', 'var/lib/k0s/pki/admin.conf'):
                path = root / secret
                if path.is_file() and path.stat().st_size: raise ValueError('Device credentials found in image: ' + secret)
            commands = [('usr/bin/bash', ['--version'], '5.3.20')] if name.startswith('core') else [('usr/bin/k0s', ['version'], 'v1.36.4+k0s.1')]
            if name == 'core-kubernetes':
                commands += [('usr/bin/kubectl', ['version', '--client', '-o', 'json'], 'v1.36.4'),
                             ('usr/bin/k0sctl', ['version'], '0.33.1'), ('usr/bin/k9s', ['version'], '0.51.0')]
            elif name == 'core':
                if (root / 'usr/bin/k0s').exists() or (root / 'usr/bin/kubectl').exists():
                    raise ValueError('The base core must not depend on Kubernetes clients')
            (temporary / 'home').mkdir()
            env = os.environ | {'HOME': str(temporary / 'home'), 'XDG_CONFIG_HOME': str(temporary / 'home/config'),
                                'XDG_CACHE_HOME': str(temporary / 'home/cache'), 'XDG_STATE_HOME': str(temporary / 'home/state')}
            for binary, args, expected in commands:
                # QEMU -L also handles the musl interpreter on an ARM64 host
                # whose own libc is glibc; no host chroot or board access.
                result = subprocess.run(['qemu-aarch64', '-L', str(root), str(root / binary), *args], env=env,
                                        capture_output=True, text=True, timeout=60)
                if result.returncode or expected not in result.stdout + result.stderr:
                    raise RuntimeError(f'{name}/{binary}: {result.stdout}{result.stderr}')
                print('PASS:', name, binary, expected)
