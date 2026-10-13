#!/usr/bin/env python3
"""Validate the installed k0s cluster, including a full reboot and NVMe persistence."""
import argparse
import json
from pathlib import Path
import shutil
import uuid
from k0s_session import exercise_k0s

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--return-ubuntu', action='store_true')
parser.add_argument('--revision', default='locals/k0s-os-070')
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/prototype-k0s-os')
args = parser.parse_args()
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
directory = ROOT / 'artifacts/k0s' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
directory.parent.chmod(0o700)
result = exercise_k0s('192.168.1.20', 2222, 6443, 30080, directory, inputs,
                      '6491b61ba229489cb8bacb1719de7c2c', expected_revision=args.revision,
                      return_ubuntu=args.return_ubuntu)
target = directory.parent / 'kubeconfig'
target.touch(mode=0o600)
shutil.copyfile(directory / 'kubeconfig', target)
target.chmod(0o600)
print('PASS: k0s node, DNS, NodePort and persistence across reboot. Logs:', directory)
print('KUBECONFIG=' + str(target))
print(json.dumps(result, indent=2))
