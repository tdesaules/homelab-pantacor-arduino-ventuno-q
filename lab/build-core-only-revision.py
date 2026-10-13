#!/usr/bin/env python3
"""Create a versioned core-only revision from a captured state and core configuration."""
import argparse
import json
from pathlib import Path
from core_only import make_core_only

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-state', type=Path, required=True)
parser.add_argument('--base-config', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
deploy = ROOT / 'artifacts/build/tmp/deploy/images/ventuno-q'
release = json.loads((deploy / 'ventuno-core-image-ventuno-q.core-release.json').read_text())
assert release['version'] == '0.4.0' and release['shells'] == {'bash': '5.3.20'}
state, objects = make_core_only(json.loads(args.base_state.read_text()), args.base_config.read_bytes(),
                                (deploy / 'ventuno-core-image-ventuno-q.squashfs').read_bytes())
args.output_dir.mkdir(parents=True, exist_ok=False)
(args.output_dir / 'objects').mkdir()
(args.output_dir / 'base-state.json').write_bytes(args.base_state.read_bytes())
for digest, data in objects.items(): (args.output_dir / 'objects' / digest).write_bytes(data)
(args.output_dir / 'state.json').write_text(json.dumps(state, sort_keys=True, separators=(',', ':')) + '\n')
(args.output_dir / 'release.json').write_text(json.dumps(release, indent=2) + '\n')
print('Prepared locals/core-only-040:', args.output_dir)
