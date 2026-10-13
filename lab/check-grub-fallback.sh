#!/usr/bin/env bash
set -euo pipefail
echo '### Current kernel and boot ID'
uname -r
cat /proc/sys/kernel/random/boot_id
echo '### GRUB defaults and one-shot state'
cat /etc/default/grub
grub-editenv /boot/grub/grubenv list
echo '### GRUB startup logic'
python3 - <<'PY'
from pathlib import Path
text = Path('/boot/grub/grub.cfg').read_text()
print(text.split('### END /etc/grub.d/00_header ###')[0])
print('\n'.join(line for line in text.splitlines() if line.startswith('menuentry ') or line.lstrip().startswith(('linux\t', 'initrd\t'))))
PY
echo '### Environment file layout'
stat /boot/grub/grubenv
filefrag -v /boot/grub/grubenv
grub-script-check /boot/grub/grub.cfg
echo '### Watchdog state (without opening the device)'
for attr in identity state timeout nowayout; do
    printf '%s: ' "$attr"
    cat "/sys/class/watchdog/watchdog0/$attr"
done
