#!/usr/bin/env python3
"""Reuse a verified BSP while qualifying new userspace images and resource policy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=ROOT / 'artifacts/prototype-1084-core-tools')
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--memory-kib', type=int, required=True)
args = parser.parse_args()
output = args.output_dir
output.mkdir(parents=True, mode=0o700, exist_ok=False)
inputs = json.loads((args.source / 'build-inputs.json').read_text())
hashes = dict((line.split()[1], line.split()[0]) for line in (args.source / 'SHA256SUMS').read_text().splitlines())
for name in ('initramfs-ventuno-q.cpio.gz', 'vendor-addon.cpio.gz', 'vmlinuz-' + inputs['kernel_release']):
    assert hashlib.sha256((args.source / name).read_bytes()).hexdigest() == hashes[name]
    shutil.copyfile(args.source / name, output / name)
shutil.copy2(args.source / 'network-host-key', output / 'network-host-key')
shutil.copyfile(args.source / 'SHA256SUMS', output / 'SHA256SUMS')
for key in ('core_image', 'k0s', 'runtime_storage', 'resource_policy'):
    inputs.pop(key, None)
inputs['copied_bsp_from'] = str(args.source)
(output / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
subprocess.run([sys.executable, str(ROOT / 'lab/build-first-revision.py'), '--output-dir', str(output),
                '--core-only', '--k0s', '--memory-kib', str(args.memory_kib)], check=True)
