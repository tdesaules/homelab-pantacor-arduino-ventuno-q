#!/usr/bin/env bash
# start: one-shot Ubuntu boot; check: verify; default: test the subsequent boot.
# Never changes grub.cfg, GRUB_DEFAULT, EFI entries or the selected kernel.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

state_path = Path('/var/tmp/ventuno-grub-fallback-test.json')
action = sys.argv[1] if len(sys.argv) == 2 else ''
if action not in ('start', 'check', 'default'):
    raise SystemExit('Usage: start | check | default')

def run(*argv):
    return subprocess.check_output(argv, text=True).strip()

def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def environment():
    return dict(line.split('=', 1) for line in run('grub-editenv', '/boot/grub/grubenv', 'list').splitlines())

def save(state):
    temporary = state_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(state_path)

def reboot():
    subprocess.run(['sync'], check=True)
    subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-fallback-reboot',
                    '/usr/bin/systemctl', 'reboot'], check=True)

boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
kernel = run('uname', '-r')
cfg = Path('/boot/grub/grub.cfg').read_text()
defaults = Path('/etc/default/grub').read_text()
subprocess.run(['grub-script-check', '/boot/grub/grub.cfg'], check=True)
if not re.search(r'^GRUB_DEFAULT=0$', defaults, re.M):
    raise SystemExit('Expected GRUB_DEFAULT=0; no changes made')
if 'save_env next_entry' not in cfg or 'set default="0"' not in cfg:
    raise SystemExit('Expected one-shot consumption/default logic absent')
if run('dpkg', '--audit'):
    raise SystemExit('Unfinished package transaction')

if action == 'start':
    if state_path.exists():
        raise SystemExit(f'Existing test record: {state_path}; inspect before starting another test')
    if environment():
        raise SystemExit('Non-empty grubenv; inspect pending state before testing')
    first = next(line for line in cfg.splitlines() if line.startswith('menuentry '))
    if not first.startswith("menuentry 'Ubuntu'"):
        raise SystemExit('First/default entry is not Ubuntu')
    match = re.search(r"\$menuentry_id_option '([^']+)'", first)
    if not match:
        raise SystemExit('Unable to identify Ubuntu entry')
    block = cfg[cfg.index(first):].split('\n}', 1)[0]
    if f'/boot/vmlinuz-{kernel} ' not in block:
        raise SystemExit('Default entry does not use the current, known-working kernel')
    state = {
        'phase': 'oneshot-waiting', 'entry': match.group(1), 'kernel': kernel,
        'previous_boot_id': boot_id, 'initial_boot_id': boot_id,
        'grub_cfg_sha256': fingerprint('/boot/grub/grub.cfg'),
        'grub_defaults_sha256': fingerprint('/etc/default/grub'),
    }
    save(state)
    subprocess.run(['grub-reboot', state['entry']], check=True)
    if environment().get('next_entry') != state['entry']:
        raise SystemExit('next_entry was not written as expected')
    print(json.dumps(state, indent=2), flush=True)
    reboot()
else:
    state = json.loads(state_path.read_text())
    if kernel != state['kernel']:
        raise SystemExit('Unexpected running kernel')
    if fingerprint('/boot/grub/grub.cfg') != state['grub_cfg_sha256'] or fingerprint('/etc/default/grub') != state['grub_defaults_sha256']:
        raise SystemExit('GRUB configuration changed during test')
    if environment().get('next_entry'):
        raise SystemExit('next_entry still present; one-shot return is not validated')
    if action == 'check':
        if state['phase'] not in ('oneshot-waiting', 'default-waiting'):
            raise SystemExit('No reboot awaiting verification')
        if boot_id == state['previous_boot_id']:
            raise SystemExit('Reboot has not occurred')
        key = 'oneshot_boot_id' if state['phase'] == 'oneshot-waiting' else 'default_boot_id'
        state[key] = boot_id
        state['phase'] = state['phase'].replace('waiting', 'verified')
        save(state)
        print('PASS: new boot ID, expected kernel, next_entry cleared, unchanged GRUB config')
        print(json.dumps(state, indent=2))
    else:
        if state['phase'] != 'oneshot-verified':
            raise SystemExit('Verify one-shot boot before the default boot test')
        state['previous_boot_id'] = boot_id
        state['phase'] = 'default-waiting'
        save(state)
        print('Testing the subsequent default boot without setting next_entry', flush=True)
        reboot()
PY
