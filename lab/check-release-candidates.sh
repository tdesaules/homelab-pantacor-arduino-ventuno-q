#!/usr/bin/env bash
set -euo pipefail
echo '### Clock and running system'
date -u
timedatectl status
cat /etc/os-release
uname -a
echo '### Cached login notifications before refresh'
for f in /var/lib/update-notifier/updates-available /var/lib/ubuntu-release-upgrader/release-upgrade-available; do
    if test -f "$f"; then stat "$f"; cat "$f"; fi
done
echo '### Refresh configured repositories'
apt-get -o APT::Update::Error-Mode=any update
echo '### Kernel and firmware candidates'
apt-cache policy linux-image-qcom linux-headers-qcom linux-generic linux-generic-hwe-24.04 linux-image-generic linux-image-generic-hwe-24.04 linux-firmware-dragonwing
apt-cache search --names-only '^linux-(image|modules|headers)-[0-9].*qcom$'
echo '### Kernel package versions'
apt-cache madison linux-image-qcom linux-generic linux-generic-hwe-24.04
echo '### Kernel metapackage dependencies'
apt-cache depends linux-image-qcom linux-generic-hwe-24.04
echo '### Remaining updates and holds'
apt-get --simulate dist-upgrade
apt-mark showhold
echo '### Release upgrade check (no upgrade)'
do-release-upgrade --check-dist-upgrade-only || printf 'Release check exit code: %s\n' "$?"
echo '### Update notifier implementation'
cat /etc/update-motd.d/90-updates-available
echo '### Sources and APT preferences'
python3 - <<'PY'
from pathlib import Path
for base in ('/etc/apt/sources.list', '/etc/apt/sources.list.d', '/etc/apt/preferences', '/etc/apt/preferences.d'):
    p = Path(base)
    paths = sorted(p.iterdir()) if p.is_dir() else [p]
    for f in paths:
        if f.is_file():
            print(f'--- {f}')
            print(f.read_text(errors='replace'))
PY
