#!/usr/bin/env bash
# Clone a clean update store for a new bounded trial; preserve the original.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

previous, trial = sys.argv[1:]
assert all(re.fullmatch('[0-9a-f]{32}', value) for value in (previous, trial)) and previous != trial
assert 'ventuno_trial=' not in Path('/proc/cmdline').read_text()
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
result = json.loads((Path('/var/lib/ventuno-trials') / previous / 'result.json').read_text())
assert result['previous_grub_restored'] and result['pid1'] == 'pantavisor'
assert result['appdata_cleanly_unmounted'] == '1' and result['runtime_cleanup_unmount_failures'] == '0'
source_dir = Path('/boot/pantavisor-diagnostic') / previous
source = source_dir / 'pvstore.ext4'
assert source.is_file() and not source.is_symlink() and source.stat().st_size == 256 * 1024 * 1024
assert not subprocess.check_output(['losetup', '-j', str(source)], text=True).strip()
stage = Path('/home/arduino/.cache/ventuno-trial-' + trial)
request = json.loads((stage / 'request.json').read_text())
inputs = json.loads((stage / 'build-inputs.json').read_text())
old_inputs = json.loads((source_dir / 'build-inputs.json').read_text())
assert request['trial_id'] == trial and inputs['pid1_runtime'] and inputs['app_storage'] == old_inputs['app_storage']

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

for name, digest in request['files'].items():
    assert '/' not in name and not (stage / name).is_symlink()
    assert sha(stage / name) == digest
for name in ('initramfs-ventuno-q.cpio.gz', 'vmlinuz-' + inputs['kernel_release']):
    assert sha(source_dir / name) == request['files'][name], 'Resume requires exactly the same tested BSP'
subprocess.run(['e2fsck', '-f', '-n', str(source)], check=True)
revision = inputs['boot_revision']
# Same safe subset as lab/revision_names.py; this runs standalone on Ubuntu.
assert re.fullmatch(r'locals/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', revision)
progress = json.loads(subprocess.check_output(['debugfs', '-R', f'cat /trails/{revision}/.pv/progress', str(source)], stderr=subprocess.DEVNULL))
assert progress['status'] in ('UPDATED', 'DONE'), 'Only a stable revision may be selected by the lab boot entry'
bootenv = subprocess.check_output(['debugfs', '-R', 'cat /boot/grubenv', str(source)], stderr=subprocess.DEVNULL, text=True)
key = 'pv_try' if progress['status'] == 'UPDATED' else 'pv_rev'
assert f'{key}={revision}' in bootenv.splitlines(), 'Selection does not match Pantavisor bootloader state'
selected = json.loads(subprocess.check_output(['debugfs', '-R', f'cat /trails/{revision}/.pvr/json', str(source)], stderr=subprocess.DEVNULL))
factory = subprocess.check_output(['debugfs', '-R', 'cat /trails/0/.pvr/json', str(source)], stderr=subprocess.DEVNULL)
assert hashlib.sha256(factory).hexdigest() == inputs['runtime_storage']['state_sha256']
baseline = json.loads(factory)
assert {k: v for k, v in selected.items() if not k.startswith('diagnostic/')} == {k: v for k, v in baseline.items() if not k.startswith('diagnostic/')}, 'Only application changes are supported by this bounded boot selector'
storage = {'revision': '0', 'size': source.stat().st_size, 'sha256': sha(source),
           'state_sha256': hashlib.sha256(factory).hexdigest()}
with source.open('rb') as src, (stage / 'pvstore.ext4.gz').open('wb') as raw:
    with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as dst: shutil.copyfileobj(src, dst)
inputs['runtime_storage'] = storage
inputs['resume_from'] = previous
(stage / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
for name in ('build-inputs.json', 'pvstore.ext4.gz'): request['files'][name] = sha(stage / name)
(stage / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
record = {'source_trial': previous, 'new_trial': trial, 'runtime_storage': storage, 'selected_revision': revision,
          'selection_from': key, 'selected_progress': progress}
(stage / 'resume-store.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['sync'], check=True)
print(json.dumps(record, indent=2))
PY
