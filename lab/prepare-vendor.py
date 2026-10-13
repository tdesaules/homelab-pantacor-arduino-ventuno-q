#!/usr/bin/env python3
"""Verify and extract pinned Debian BSP packages without running maintainer scripts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'bsp/vendor-packages.json').read_text())
output = root / 'artifacts/vendor-extracted'
output.mkdir(exist_ok=True)
for package in manifest['packages']:
    archive = root / 'artifacts/vendor' / package['url'].rsplit('/', 1)[1]
    with archive.open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == package['sha256'], archive
    destination = output / package['name']
    if destination.exists():
        raise SystemExit(f'Refusing to overwrite existing extraction: {destination}')
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        tmp = Path(tmp)
        members = subprocess.check_output(['ar', 't', str(archive)], text=True).splitlines()
        member, = [name for name in members if name == 'data.tar' or name.startswith('data.tar.')]
        data = tmp / member
        with data.open('wb') as stream:
            subprocess.run(['ar', 'p', str(archive), member], stdout=stream, check=True)
        unpack = tmp / 'root'
        unpack.mkdir()
        subprocess.run(['tar', '-xf', str(data), '--no-same-owner', '-C', str(unpack)], check=True)
        shutil.move(unpack, destination)
    print(f'Extracted verified package: {destination}')
