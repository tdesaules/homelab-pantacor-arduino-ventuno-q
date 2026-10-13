#!/usr/bin/env bash
# Remove only this installation's GRUB entry; keep its store, logs and NVMe data.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

install_id = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', install_id)
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
audit = Path('/var/lib/ventuno-autonomous') / install_id
record = json.loads((audit / 'installation.json').read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
config = Path('/boot/grub/grub.cfg')
snippet = Path('/etc/grub.d/41_ventuno_persistent')
assert sha(config) == record['installed_grub_sha256'], 'GRUB changed externally; inspect before restoring'
assert sha(Path('/etc/default/grub')) == record['defaults_sha256']
assert sha(snippet) == record['snippet_sha256']
default_snippet = Path('/etc/grub.d/09_ventuno_default')
if 'default_snippet_sha256' in record:
    assert sha(default_snippet) == record['default_snippet_sha256']
else:
    assert not default_snippet.exists()
assert sha(audit / 'grub.cfg.before') == record['before_grub_sha256']
env = dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines())
assert env.get('next_entry', '') in ('', 'pantavisor-persistent')
subprocess.run(['grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry'], check=True)
candidate = audit / 'grub.cfg.restore'
shutil.copy2(audit / 'grub.cfg.before', candidate)
subprocess.run(['grub-script-check', str(candidate)], check=True)
os.replace(candidate, config)
snippet.unlink()
if default_snippet.exists(): default_snippet.unlink()
subprocess.run(['sync'], check=True)
print('Persistent menu entry removed and previous GRUB restored. Store and NVMe data retained.')
PY
