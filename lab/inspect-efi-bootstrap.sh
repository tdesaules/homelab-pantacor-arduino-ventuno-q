#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
efibootmgr -v
cat /proc/cmdline
ls -l /boot/efi/EFI/ubuntu /boot/efi/EFI/BOOT
for file in /boot/efi/EFI/ubuntu/grub.cfg /boot/efi/EFI/BOOT/grub.cfg; do
    if [ -f "$file" ]; then printf '\n%s\n' "$file"; cat "$file"; fi
done
sha256sum /boot/grub/grub.cfg
