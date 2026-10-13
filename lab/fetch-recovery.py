#!/usr/bin/env python3
"""Download and verify the official recovery image and flasher; never flash."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
dest = root / 'artifacts/recovery'
dest.mkdir(exist_ok=True)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def fetch(item):
    path = dest / item['name']
    if path.exists() and digest(path) == item['sha256']:
        print('Verified cached:', path.name, flush=True)
        return
    temporary = path.with_name(path.name + '.part')
    try:
        with urllib.request.urlopen(item['url'], timeout=120) as source, temporary.open('wb') as target:
            while chunk := source.read(4 * 1024 * 1024):
                target.write(chunk)
        if digest(temporary) != item['sha256']:
            raise ValueError('Checksum mismatch: ' + item['name'])
        temporary.replace(path)
        print('Downloaded and verified:', path.name, path.stat().st_size, 'bytes', flush=True)
    finally:
        temporary.unlink(missing_ok=True)

items = json.loads((root / 'bsp/recovery-downloads.json').read_text())['files']
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(fetch, items))
