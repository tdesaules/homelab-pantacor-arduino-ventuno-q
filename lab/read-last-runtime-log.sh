#!/usr/bin/env bash
set -euo pipefail
python3 - "$@" <<'PY'
import subprocess
import sys
import uuid
from pathlib import Path

image = '/boot/pantavisor/pvstore.ext4'
if len(sys.argv) > 1:
    boot = str(uuid.UUID(sys.argv[1]))
    text = (Path('/boot/pantavisor/logs') / (boot + '.log')).read_text(errors='replace')
    for heading in ('### DHCP and SSH', '### Pantavisor containers', '### Revision progress', '### Persistent application data'):
        if heading in text:
            print('\n'.join(text.split(heading, 1)[1].splitlines()[:12]))
    raise SystemExit(0)
def read(command):
    return subprocess.check_output(['debugfs', '-R', command, image], stderr=subprocess.DEVNULL, text=True, errors='replace')
directory = '/logs/locals/app-v2/pantavisor'
listing = read('ls -p ' + directory)
print(listing)
for line in listing.splitlines():
    fields = line.split('/')
    if len(fields) < 7 or not fields[2].startswith('10'): continue
    name = fields[5]
    if name in ('.', '..') or not name: continue
    text = read('cat ' + directory + '/' + name)
    print('### ' + name)
    events = [line for line in text.splitlines() if any(key in line for key in ('signal-ep', 'status is now', 'status goal timed', 'Unexpected', 'ERROR'))]
    print('\n'.join(events[-60:]))
    print('\n'.join(text.splitlines()[-45:]))
PY
