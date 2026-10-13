#!/usr/bin/env bash
# Read-only inventory before a one-shot independent recovery qualification.
set -euo pipefail
test "$(id -u)" -eq 0
uname -a
cat /proc/cmdline
findmnt --target /
findmnt --target /boot/efi
lsblk -o NAME,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS /dev/mmcblk0
df -h /boot/efi
efibootmgr -v || true
if command -v mokutil >/dev/null; then mokutil --sb-state; fi
grub-editenv /boot/grub/grubenv list
grub-editenv /boot/pantavisor/state/boot-budget list
grub-editenv /boot/pantavisor/state/grubenv list
sha256sum /boot/pantavisor/kernel /boot/pantavisor/initramfs
cat /boot/pantavisor/install-id
