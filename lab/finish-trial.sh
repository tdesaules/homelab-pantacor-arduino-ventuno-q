#!/usr/bin/env bash
# Collect evidence and restore the exact previous GRUB configuration if unchanged.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

trial = sys.argv[1] if len(sys.argv) == 2 else ''
assert re.fullmatch('[0-9a-f]{32}', trial)
backup = Path('/var/lib/ventuno-trials') / trial
record = json.loads((backup / 'installation.json').read_text())
started = json.loads((backup / 'started.json').read_text())
boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot_id != started['before_boot_id'], 'No reboot observed'
assert 'ventuno_trial=' not in Path('/proc/cmdline').read_text(), 'Still running the prototype'
assert subprocess.check_output(['uname', '-r'], text=True).strip() == record['kernel_release']
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert sha(Path('/boot/grub/grub.cfg')) == record['installed_grub_sha256'], 'GRUB changed externally; inspect before restoring'
assert sha(Path('/etc/default/grub')) == record['before_defaults_sha256']
assert sha(backup / 'grub.cfg.before') == record['before_grub_sha256']
snippet = Path('/etc/grub.d') / ('41_ventuno_trial_' + trial)
assert sha(snippet) == record['snippet_sha256']
env = dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).splitlines())
pending = env.get('next_entry')
if pending == record['entry_id']:
    subprocess.run(['grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry'], check=True)
elif pending:
    raise SystemExit('Another next_entry is queued; inspect before restoring')
temporary = Path('/boot/grub/grub.cfg.ventuno-restore-' + trial)
shutil.copy2(backup / 'grub.cfg.before', temporary)
subprocess.run(['grub-script-check', str(temporary)], check=True)
os.replace(temporary, '/boot/grub/grub.cfg')
snippet.unlink()
logfile = Path('/boot/pantavisor-diagnostic') / trial / 'trial.log'
text = logfile.read_text(errors='replace') if logfile.exists() else ''

def field(key):
    found = re.search('^' + re.escape(key) + '=(.*)$', text, re.M)
    return found.group(1) if found else None

result = {
    'trial_id': trial, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'return_seconds': started['return_seconds'],
    'selected_boot_revision': record.get('boot_revision', '0'),
    'ubuntu_boot_id': boot_id, 'before_boot_id': started['before_boot_id'],
    'prototype_boot_id': field('TRIAL_BOOT_ID'), 'pid1': field('HOST_PID1_NAME') or field('PID1_NAME'),
    'pid1_exe': field('HOST_PID1_EXE'),
    'pantavisor_reboot_requested': field('PANTAVISOR_REBOOT_REQUESTED'),
    'pantavisor_storage_unmounted': field('PANTAVISOR_STORAGE_UNMOUNTED'),
    'appdata_uuid': field('APPDATA_UUID'),
    'appdata_cleanly_unmounted': field('APPDATA_CLEANLY_UNMOUNTED'),
    'bootstrap_stage': field('BOOTSTRAP_STAGE'),
    'pantavisor_state': field('pantavisor_state'), 'pantavisor_exit': field('pantavisor_exit'),
    'pantavisor_version_exit': field('PANTAVISOR_VERSION_EXIT'),
    'dhcp_bound': field('DHCP_BOUND'), 'dhcp_address': field('address'),
    'network_owner': field('NETWORK_OWNER'), 'host_network_pid': field('network_pid'),
    'wifi_interface_count': field('WIFI_INTERFACE_COUNT'),
    'runtime_status_exit': field('RUNTIME_STATUS_EXIT'),
    'runtime_cleanup_unmount_failures': field('RUNTIME_CLEANUP_UNMOUNT_FAILURES'),
    'diagnostics_started': 'TRIAL_STARTED=' + trial in text,
    'diagnostics_complete': 'TRIAL_DIAGNOSTICS_COMPLETE=' + trial in text,
    'driver_check_exit': field('DRIVER_CHECK_EXIT'), 'nvme_read_exit': field('NVME_READ_EXIT'),
    'watchdog': field('watchdog'), 'watchdog_timeout': field('watchdog_timeout'),
    'next_entry_was_cleared': not pending, 'previous_grub_restored': True,
}
(backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
subprocess.run(['sync'], check=True)
print(json.dumps(result, indent=2))
print('### Complete prototype diagnostic log')
print(text or '(No diagnostic log: logging was not reached or failed; boot stage is unknown.)')
image = logfile.parent / 'pvstore.ext4'
if image.exists():
    print('### Persisted container data after reboot')
    subprocess.run(['e2fsck', '-f', '-n', str(image)], check=True)
    env = subprocess.check_output(['debugfs', '-R', 'cat /boot/grubenv', str(image)], stderr=subprocess.DEVNULL, text=True)
    result['private_boot_env'] = dict(line.split('=', 1) for line in env.splitlines() if line.startswith(('pv_rev=', 'pv_try=')))
    result['local_revision_progress'] = {}
    for revision in ('locals/app-v1', 'locals/app-v2', 'locals/app-unready'):
        progress = subprocess.check_output(['debugfs', '-R', f'cat /trails/{revision}/.pv/progress', str(image)], stderr=subprocess.DEVNULL, text=True)
        if progress.strip(): result['local_revision_progress'][revision] = json.loads(progress)
    (backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('### Private Pantavisor boot state and local revisions')
    print(json.dumps({'boot_env': result['private_boot_env'], 'progress': result['local_revision_progress']}, indent=2))
    inputs = json.loads((logfile.parent / 'build-inputs.json').read_text())
    if inputs.get('app_storage'):
        profile = inputs['app_storage']
        assert field('APPDATA_UUID') == profile['filesystem_uuid']
        assert field('APPDATA_CLEANLY_UNMOUNTED') == '1'
        device = Path('/dev/disk/by-uuid') / profile['filesystem_uuid']
        assert device.resolve() == Path('/dev/nvme0n1p1')
        assert Path('/sys/class/nvme/nvme0/serial').read_text().strip() == profile['serial']
        assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(device)], text=True).strip()
        subprocess.run(['e2fsck', '-f', '-n', str(device)], check=True)
        for name in ('boots', 'heartbeat.json', 'identity'):
            subprocess.run(['debugfs', '-R', 'cat /perm/diagnostic/data/' + name, str(device)], check=True)
        fallback = subprocess.check_output(['debugfs', '-R', 'stat /disks/perm/diagnostic/data', str(image)], stderr=subprocess.DEVNULL, text=True)
        assert 'Inode:' not in fallback, 'Unexpected application data on eMMC'
        print('APPDATA_NVME_VERIFIED_AFTER_REBOOT=1')
    else:
        for path in ('/disks/perm/diagnostic/data/boots', '/disks/perm/diagnostic/data/heartbeat.json'):
            subprocess.run(['debugfs', '-R', 'cat ' + path, str(image)], check=True)
    if field('NETWORK_OWNER') in ('revision', 'core'):
        name = 'core' if field('NETWORK_OWNER') == 'core' else 'network'
        subprocess.run(['debugfs', '-R', f'cat /disks/perm/{name}/data/boots', str(image)], check=True)
PY
echo '### Ubuntu services after return'
systemctl --failed --no-pager
systemctl is-active ssh NetworkManager arduino-app-cli arduino-router
