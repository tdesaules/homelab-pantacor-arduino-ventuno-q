#!/usr/bin/env bash
# Read-only evidence collection when diagnostic SSH is unavailable.
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

def run(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}

root = Path('/boot/pantavisor')
result = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'cmdline': Path('/proc/cmdline').read_text().strip(),
          'uptime': Path('/proc/uptime').read_text().strip(),
          'main_env': run('grub-editenv', '/boot/grub/grubenv', 'list'),
          'pv_env': run('grub-editenv', str(root / 'state/grubenv'), 'list'),
          'budget': run('grub-editenv', str(root / 'state/boot-budget'), 'list')}
logs = sorted((root / 'logs').glob('*.log'))
result['logs'] = []
for log in logs:
    text = log.read_text(errors='replace')
    lines = text.splitlines()
    result['logs'].append({'name': log.name, 'mtime': log.stat().st_mtime, 'bytes': log.stat().st_size,
                          'markers': [line for line in lines if line.startswith(('TRIAL_BOOT_ID=', 'APPDATA_', 'AUTONOMOUS_', 'HOST_PID1_', 'RUNTIME_', 'STORAGE_'))],
                          'errors': [line for line in lines if not line.startswith('[') and any(word in line.lower() for word in ('error', 'failed', 'invalid', 'not found'))],
                          'last_lines': lines[-5:]})
result['store_header'] = run('dumpe2fs', '-h', str(root / 'pvstore.ext4'))
result['nvme_header'] = run('dumpe2fs', '-h', '/dev/nvme0n1p1')
result['runtime_log_dirs'] = run('debugfs', '-R', 'ls -l /logs/locals/app-v2', str(root / 'pvstore.ext4'))
result['boots'] = run('journalctl', '--list-boots', '--no-pager')
result['previous_shutdown'] = run('journalctl', '-b', '-1', '-n', '50', '--no-pager')
print(json.dumps(result, indent=2))
PY
