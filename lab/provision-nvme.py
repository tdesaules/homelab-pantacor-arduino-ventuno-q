#!/usr/bin/env python3
"""Provision the explicitly identified, empty lab NVMe once, using the pinned profile."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
profile = json.loads((root / 'bsp/nvme-app-storage.json').read_text())
subprocess.run([sys.executable, str(root / 'lab/run-board-check.py'), '--sudo',
                '--argument', json.dumps(profile), str(root / 'lab/provision-nvme.sh')], check=True)
