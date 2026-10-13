#!/usr/bin/env python3
"""Archive the board's boot files and live FDT over SSH (not a full disk backup)."""
import hashlib
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bsp', action='store_true', help='Include installed modules, firmware and module configuration')
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/board-reference', help='New local directory for a separate capture')
args = parser.parse_args()
output = args.output_dir
output.mkdir(parents=True, exist_ok=True)
archive = output / ('board-bsp-reference.tar.gz' if args.bsp else 'ubuntu-boot-reference.tar.gz')
if archive.exists():
    raise SystemExit(f'Refusing to overwrite {archive}')
password = re.search(r'Mot de passe : `([^`]+)`', (root / 'docs/access.local.md').read_text()).group(1)
remote = '''import io, json, pathlib, subprocess, sys, tarfile
release = subprocess.check_output(["uname", "-r"], text=True).strip()
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as tar:
    for path in PATHS:
        path = path.replace("KERNEL_RELEASE", release)
        tar.add(path, arcname=path.lstrip("/"))
    for name, data in (
        ("live.dtb", pathlib.Path("/sys/firmware/fdt").read_bytes()),
        ("emmc-gpt.txt", subprocess.check_output(["sfdisk", "--dump", "/dev/mmcblk0"])),
        ("efi-boot-entries.txt", subprocess.check_output(["efibootmgr", "-v"])),
        ("kernel-release.txt", (release + "\\n").encode()),
        ("packages.tsv", subprocess.check_output(["dpkg-query", "-W", "-f=${Package}\\t${Version}\\n"])),
    ):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
'''
paths = ['/boot', '/etc/default/grub', '/etc/grub.d']
if args.bsp:
    paths += ['/lib/modules/KERNEL_RELEASE', '/lib/firmware', '/etc/modprobe.d', '/usr/lib/modprobe.d']
remote = remote.replace('PATHS', repr(paths))
env = os.environ | {'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
temporary = archive.with_suffix('.part')
with temporary.open('wb') as stream:
    result = subprocess.run([
        'ssh', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
        '-o', 'ConnectTimeout=10', '-o', 'NumberOfPasswordPrompts=1',
        'arduino@192.168.1.20', "sudo -S -p '' python3 -c " + shlex.quote(remote),
    ], input=(password + '\n').encode(), stdout=stream, env=env, timeout=300)
if result.returncode:
    temporary.unlink(missing_ok=True)
    raise SystemExit(result.returncode)
temporary.replace(archive)
with archive.open('rb') as stream:
    checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
(output / (archive.name + '.sha256')).write_text(f'{checksum}  {archive.name}\n')
print(f'Boot reference: {archive}; SHA256={checksum}')
