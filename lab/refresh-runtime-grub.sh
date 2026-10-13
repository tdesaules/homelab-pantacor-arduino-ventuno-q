#!/usr/bin/env bash
# Refresh only the checked GRUB policy of an already upgraded installation.
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

upgrade_id = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', upgrade_id)
stage = Path('/home/arduino/.cache/ventuno-runtime-upgrade-' + upgrade_id)
request = json.loads((stage / 'request.json').read_text())
install_id = request['install_id']
assert re.fullmatch('[0-9a-f]{32}', install_id)
assert request['upgrade_id'] == upgrade_id
root = Path('/boot/pantavisor')
assert (root / 'install-id').read_text().strip() == install_id
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '/'], text=True).strip() == request['root_uuid']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
audit = Path('/var/lib/ventuno-autonomous') / install_id
record_path = audit / 'installation.json'
record = json.loads(record_path.read_text())
assert sha(root / 'initramfs') == request['files']['initramfs'] == record['files']['initramfs']
config = Path('/boot/grub/grub.cfg')
assert sha(config) == record['installed_grub_sha256']
budget = subprocess.check_output(['grub-editenv', str(root / 'state/boot-budget'), 'list'], text=True)
assert 'ventuno_recovery=1\n' in budget
snippets = [('grub-default.cfg', Path('/etc/grub.d/09_ventuno_default'), 'default_snippet_sha256'),
            ('grub-entry.cfg', Path('/etc/grub.d/41_ventuno_persistent'), 'snippet_sha256')]
for source, target, key in snippets:
    assert sha(target) == record[key]
    assert sha(stage / source) == request['files'][source]
    subprocess.run(['grub-script-check', str(stage / source)], check=True)
backup = audit / ('grub-refresh-' + upgrade_id)
backup.mkdir(mode=0o700)
shutil.copy2(config, backup / 'grub.cfg')
shutil.copy2(record_path, backup / 'installation.json')
for _, target, _ in snippets: shutil.copy2(target, backup / target.name)
try:
    for source, target, key in snippets:
        target.write_text("#!/bin/sh\ncat <<'VENTUNO_EOF'\n" + (stage / source).read_text() + 'VENTUNO_EOF\n')
        target.chmod(0o755)
        record[key] = sha(target)
    candidate = backup / 'grub.cfg.candidate'
    result = subprocess.run(['grub-mkconfig', '-o', str(candidate)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (backup / 'grub-mkconfig.log').write_text(result.stdout)
    result.check_returncode()
    subprocess.run(['grub-script-check', str(candidate)], check=True)
    assert next(line for line in candidate.read_text().splitlines() if line.startswith('menuentry ')).startswith("menuentry 'Ubuntu'")
    os.replace(candidate, config)
    record['installed_grub_sha256'] = sha(config)
    record['grub_refresh'] = {'backup': str(backup), 'upgrade_id': upgrade_id}
    record_path.write_text(json.dumps(record, indent=2) + '\n')
except BaseException:
    for _, target, _ in snippets: shutil.copy2(backup / target.name, target)
    shutil.copy2(backup / 'grub.cfg', config)
    shutil.copy2(backup / 'installation.json', record_path)
    raise
subprocess.run(['sync'], check=True)
print('GRUB refreshed with direct recovery on environment write failure. Backup:', backup)
PY
