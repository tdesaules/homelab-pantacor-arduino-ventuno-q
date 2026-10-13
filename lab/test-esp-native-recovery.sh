#!/usr/bin/env bash
# One-shot ESP-only handoff through the firmware-supported factory loader.
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

token = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', token)
directory = Path('/var/lib/ventuno-native-recovery') / token
record = json.loads((directory / 'trial.json').read_text())
assert hashlib.sha256(Path('/boot/grub/grub.cfg').read_bytes()).hexdigest() == record['grubSha256']
assert hashlib.sha256(Path(record['efi']).read_bytes()).hexdigest() == record['efiSha256']
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert 'BootNext:' not in subprocess.check_output(['efibootmgr'], text=True)
target = Path('/boot/efi/EFI/ubuntu/grub.cfg')
old = target.read_bytes()
assert b'e5defb48-4df4-40fc-8f97-7d635b46fcb8' in old and len(old) < 256
backup = directory / 'esp-grub.cfg.before'
assert not backup.exists()
shutil.copy2(target, backup)
esp_path = '/EFI/ventuno-trial-' + token
env = Path('/boot/efi' + esp_path + '/once.env')
data = b'# GRUB Environment Block\nnative_trial=1\n'
with env.open('xb') as stream:
    stream.write(data + b'#' * (1024 - len(data))); stream.flush(); os.fsync(stream.fileno())
text = f'''# One-shot native recovery; fallback below is the unchanged factory bootstrap.
insmod part_gpt
insmod fat
insmod loadenv
insmod chain
search --no-floppy --fs-uuid --set=ventuno_esp 78B2-3FE4
set native_trial=0
if load_env -f ($ventuno_esp){esp_path}/once.env native_trial; then
    if [ "$native_trial" = 1 ]; then
        set native_trial=0
        if save_env -f ($ventuno_esp){esp_path}/once.env native_trial; then
            echo 'VENTUNO_ESP_ONLY_RECOVERY'
            if chainloader ($ventuno_esp){esp_path}/recoveryaa64.efi; then
                boot
            fi
        fi
    fi
fi
'''.encode() + old
temporary = target.with_name('grub.cfg.native-trial')
assert not temporary.exists()
with temporary.open('xb') as stream:
    stream.write(text); stream.flush(); os.fsync(stream.fileno())
subprocess.run(['grub-script-check', str(temporary)], check=True)
record.update({'espBootstrapBefore': hashlib.sha256(old).hexdigest(),
               'espBootstrapTrial': hashlib.sha256(text).hexdigest(), 'onceEnv': str(env)})
(directory / 'trial.json').write_text(json.dumps(record, indent=2) + '\n')
temporary.replace(target)
subprocess.run(['sync'], check=True)
subprocess.run(['systemd-run', '--on-active=5s', '--unit=ventuno-rescue-esp', '/usr/bin/systemctl', 'reboot'], check=True)
print('ESP-only one-shot rescue scheduled; factory bootstrap saved and retained as fallback.')
PY
