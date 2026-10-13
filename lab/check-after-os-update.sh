#!/usr/bin/env bash
set -euo pipefail
date -u
echo '### Boot identity'
cat /proc/sys/kernel/random/boot_id
uptime -s
uname -a
cat /etc/os-release /etc/buildinfo
echo '### Package consistency and remaining upgrades'
dpkg --audit
apt-get check
apt-get --simulate dist-upgrade
apt-mark showhold
snap refresh --list
snap list
echo '### BSP and Arduino versions'
dpkg-query -W '-f=${Package} ${Version}\n' \
    "linux-image-$(uname -r)" "linux-modules-$(uname -r)" \
    linux-image-qcom linux-firmware linux-firmware-dragonwing \
    arduino-app-cli arduino-app-lab arduino-router arduino-ventunoq-config \
    arduino-ventunoq openssh-server network-manager
echo '### Services'
systemctl --failed --no-pager
systemctl is-active ssh NetworkManager arduino-app-cli arduino-router
echo '### Storage and network'
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL
ip -br address
ethtool end0
nmcli device status
nmcli -f CHAN,FREQ,SIGNAL,SECURITY device wifi list ifname wlp3s0 --rescan yes
lsusb -t
echo '### Reboot requirement'
if test -f /var/run/reboot-required; then
    cat /var/run/reboot-required /var/run/reboot-required.pkgs
else
    echo 'No reboot-required marker'
fi
echo '### Kernel errors this boot'
journalctl -k -b -p err --no-pager
