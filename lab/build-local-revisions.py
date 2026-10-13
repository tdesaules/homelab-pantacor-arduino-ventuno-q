#!/usr/bin/env python3
"""Build application-only local update manifests and new content-addressed objects."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from initramfs_archive import newc_members

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-1084-updates')
args = parser.parse_args()
output = args.output_dir
state = json.loads((output / 'revision-0.json').read_text())
entries = {n: data for n, mode, data in newc_members(gzip.decompress((output / 'initramfs-ventuno-q.cpio.gz').read_bytes()))}
directory = output / 'local-revisions'
directory.mkdir(exist_ok=True)
(directory / 'objects').mkdir(exist_ok=True)
manifest = {}
for name, image, version in (('app-v1', 'diagnostic', '1.0.0'), ('app-v2', 'diagnostic-v2', '2.0.0'),
                              ('app-unready', 'diagnostic-unready', '2.0.0-unready')):
    data = entries['usr/share/ventuno/' + image + '.squashfs']
    digest = hashlib.sha256(data).hexdigest()
    (directory / 'objects' / digest).write_bytes(data)
    revision = state | {'diagnostic/root.squashfs': digest}
    assert all(revision[key] == state[key] for key in state if key != 'diagnostic/root.squashfs')
    (directory / (name + '.json')).write_text(json.dumps(revision, sort_keys=True, separators=(',', ':')) + '\n')
    manifest[name] = {'revision': 'locals/' + name, 'application_version': version, 'rootfs_sha256': digest}
(directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Prepared application-only local revisions:', directory)
