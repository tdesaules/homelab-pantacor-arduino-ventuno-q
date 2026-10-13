#!/usr/bin/env python3
"""Download the pinned BSP packages, rejecting any checksum mismatch."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
packages = json.loads((root / 'bsp/vendor-packages.json').read_text())['packages']
dest = root / 'artifacts/vendor'
dest.mkdir(parents=True, exist_ok=True)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def fetch(package):
    path = dest / package['url'].rsplit('/', 1)[1]
    if path.exists() and digest(path) == package['sha256']:
        print(f'Cached and verified: {path.name}', flush=True)
        return
    temporary = path.with_suffix(path.suffix + '.part')
    try:
        with urllib.request.urlopen(package['url'], timeout=120) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if digest(temporary) != package['sha256']:
            raise RuntimeError(f'Checksum mismatch: {package["name"]}')
        temporary.replace(path)
        print(f'Downloaded and verified: {path.name}', flush=True)
    finally:
        temporary.unlink(missing_ok=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    list(executor.map(fetch, packages))
