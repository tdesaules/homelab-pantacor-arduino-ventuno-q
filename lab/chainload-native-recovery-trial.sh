#!/usr/bin/env bash
# Fallback diagnostic for firmware that does not preserve the BootNext entry.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

token = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', token)
directory = Path('/var/lib/ventuno-native-recovery') / token
record = json.loads((directory / 'trial.json').read_text())
grub = Path('/boot/grub/grub.cfg')
assert hashlib.sha256(grub.read_bytes()).hexdigest() == record['grubSha256']
assert hashlib.sha256(Path(record['efi']).read_bytes()).hexdigest() == record['efiSha256']
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert 'ventuno_recovery=1' in subprocess.check_output(['grub-editenv', '/boot/pantavisor/state/boot-budget', 'list'], text=True)
assert not subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True).strip()
assert 'BootNext:' not in subprocess.check_output(['efibootmgr'], text=True)
shutil.copy2(grub, directory / 'grub.cfg.before')
entry = 'ventuno-native-recovery-' + token
snippet = Path('/etc/grub.d') / ('42_' + entry)
assert not snippet.exists()
snippet.write_text(f'''#!/bin/sh
exec tail -n +3 $0
menuentry 'Ventuno independent recovery test' --id {entry} {{
    insmod part_gpt
    insmod fat
    insmod chain
    search --no-floppy --fs-uuid --set=rescue_esp 78B2-3FE4
    echo 'VENTUNO_RESCUE_CHAINLOAD'
    if chainloader ($rescue_esp)/EFI/ventuno-trial-{token}/recoveryaa64.efi; then
        boot
    fi
    echo 'VENTUNO_RESCUE_CHAINLOAD_RETURNED'
    sleep 10
    set ventuno_force_ubuntu=1
    export ventuno_force_ubuntu
    search --no-floppy --fs-uuid --set=root e5defb48-4df4-40fc-8f97-7d635b46fcb8
    configfile ($root)/boot/grub/grub.cfg
}}
''')
snippet.chmod(0o755)
subprocess.run(['update-grub'], check=True)
subprocess.run(['grub-script-check', str(grub)], check=True)
record.update({'chainEntry': entry, 'snippet': str(snippet),
               'chainGrubSha256': hashlib.sha256(grub.read_bytes()).hexdigest()})
(directory / 'trial.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['grub-reboot', entry], check=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-rescue-chainload', '/usr/bin/systemctl', 'reboot'], check=True)
print('One-shot GRUB chainload scheduled:', entry)
PY
