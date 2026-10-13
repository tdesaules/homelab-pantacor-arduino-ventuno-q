#!/usr/bin/env bash
# Read-only inventory. Each command's status is printed, including missing tools.
set -u
check() { printf '\n### %s\n' "$*"; "$@"; printf 'exit=%s\n' "$?"; }
check date -u
check uname -a
check sudo -n true
check lsblk -o NAME,SIZE,TYPE,FSTYPE,PARTLABEL,MOUNTPOINTS,MODEL
check ls -l /boot /boot/efi /sys/firmware/efi /sys/class/udc
check efibootmgr -v
check cat /etc/default/grub
check bash -c 'grep -E "menuentry |linux |initrd |devicetree|chainloader" /boot/grub/grub.cfg'
check dpkg-query -W '-f=${Package} ${Version} ${source:Package} ${source:Version}\n' 'linux-*' '*firmware*' '*grub*'
check bash -c 'grep -rhE "^(deb |URIs:|Suites:|Components:)" /etc/apt/sources.list /etc/apt/sources.list.d 2>/dev/null'
check bash -c 'grep -E "CONFIG_(NAMESPACES|.*_NS|CGROUP.*|MEMCG.*|CPUSETS|VETH|BRIDGE|OVERLAY_FS|SQUASHFS.*|BLK_DEV_LOOP|DM_CRYPT|DM_VERITY|SECCOMP.*|EXT4_FS|NVME.*|USB_CONFIGFS.*|USB_GADGET.*|DEVTMPFS.*)=" /boot/config-$(uname -r)'
check cat /proc/cgroups /sys/fs/cgroup/cgroup.controllers
check lspci -nnk
check ethtool end0
check ethtool -i end0
check ethtool -i wlp3s0
check rfkill list
check nmcli -f GENERAL,WIFI-PROPERTIES device show wlp3s0
check lsusb -t
check bash -c 'for f in /sys/class/thermal/thermal_zone*/temp; do printf "%s " "$f"; cat "$f"; done'
check journalctl -k -b -p warning --no-pager
check bash -c 'for c in mksquashfs unshare mount docker lxc-checkconfig nvme smartctl fio mkfs.ext4; do command -v "$c"; done'
