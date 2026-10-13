#!/usr/bin/env python3
"""Verify the upgraded runtime over pinned SSH; optionally return to Ubuntu."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid
from core_only import core_only_ready
from local_updates import Session
from persistent_session import fields, wait_boot
from runtime_validation import section

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--return-ubuntu', action='store_true')
args = parser.parse_args()
output = ROOT / 'artifacts/prototype-1084-recovery'
inputs = json.loads((output / 'build-inputs.json').read_text())
logs = output / 'hardware' / uuid.uuid4().hex
logs.mkdir(parents=True)
session = Session('192.168.1.20', 2222, logs)
boot = wait_boot(session, '6491b61ba229489cb8bacb1719de7c2c', timeout=240)
until = time.monotonic() + 240
while time.monotonic() < until:
    try:
        text = session.snapshot('runtime-active')
        if core_only_ready(text, 'locals/runtime-041', inputs['core_image']['release']):
            guard = fields(text, '### Host PID 1')
            if int(guard['elapsed']) >= 180:
                assert guard['watchdog'] == 'armed'
                state, _ = json.JSONDecoder().raw_decode(section(text, '### Current revision'))
                assert state['bsp/pantavisor'] == hashlib.sha256((output / 'initramfs-ventuno-q.cpio.gz').read_bytes()).hexdigest()
                assert state['core/root.squashfs'] == inputs['core_image']['sha256']
                break
    except (RuntimeError, subprocess.TimeoutExpired): pass
    time.sleep(5)
else: raise RuntimeError('Upgraded revision failed to become stable DONE/READY')
session.shells(inputs)
storage = session.run('cat /trial-status/app-storage.status')
assert 'APPDATA_MOUNTED=1' in storage
(logs / 'result.json').write_text(json.dumps({'revision': 'locals/runtime-041', 'status': 'DONE',
    'core_boot_id': boot, 'guard': guard, 'app_storage': storage}, indent=2) + '\n')
print('PASS: upgraded runtime DONE, core READY, watchdog armed and SSH shells functional. Logs:', logs)
if args.return_ubuntu: session.reboot_command('ventuno-reboot ubuntu')
