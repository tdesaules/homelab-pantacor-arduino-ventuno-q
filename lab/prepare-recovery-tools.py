#!/usr/bin/env python3
"""Prepare the verified CLI locally and cache hardware reference PDFs."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
dest = root / 'artifacts/recovery'
item = json.loads((root / 'bsp/recovery-downloads.json').read_text())['files'][0]
archive = dest / item['name']
with archive.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']
tools = dest / 'flasher-0.5.4'
tools.mkdir(exist_ok=True)
with tarfile.open(archive) as tar:
    tar.extractall(tools, filter='data')
subprocess.run([str(tools / 'arduino-flasher-cli'), 'version'], check=True)
references = {}
for name, url in {
    'schematics': 'https://docs.arduino.cc/resources/schematics/ABX00181-schematics.pdf',
    'pinout': 'https://docs.arduino.cc/resources/pinouts/ABX00181-full-pinout.pdf',
}.items():
    path = dest / f'{name}.pdf'
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    path.write_bytes(content)
    subprocess.run(['pdftotext', '-layout', str(path), str(path.with_suffix('.txt'))], check=True)
    references[name] = {'url': url, 'sha256': hashlib.sha256(content).hexdigest()}
    print(name, references[name]['sha256'])
(dest / 'hardware-reference-sources.json').write_text(json.dumps(references, indent=2) + '\n')
