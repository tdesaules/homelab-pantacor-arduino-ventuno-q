#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
date -u
uname -a
cat /etc/os-release /etc/buildinfo
df -h / /boot/efi
dpkg --audit
apt-mark showhold
systemctl --failed --no-pager
echo '### Refresh APT indexes'
apt-get -o APT::Update::Error-Mode=any update
echo '### Simulated upgrade'
apt-get --simulate dist-upgrade
echo '### Snap updates'
if command -v snap >/dev/null; then
    snap refresh --list
    snap changes
fi
echo '### Arduino upgrade services and packages'
dpkg-query -W '-f=${db:Status-Abbrev} ${Package} ${Version}\n' '*arduino*' '*sysupgrade*' '*fwupd*' || true
systemctl list-unit-files --no-pager '*arduino*' '*upgrade*' '*fwupd*'
