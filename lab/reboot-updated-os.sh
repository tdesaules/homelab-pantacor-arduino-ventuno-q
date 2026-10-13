#!/usr/bin/env bash
set -euo pipefail
test "$(systemctl show -p SubState --value ventuno-os-update)" = exited
test "$(systemctl show -p Result --value ventuno-os-update)" = success
test -z "$(dpkg --audit)"
grub-script-check /boot/grub/grub.cfg
echo '### Boot ID before reboot'
cat /proc/sys/kernel/random/boot_id
echo '### Available kernels'
ls -lh /boot/vmlinuz-* /boot/initrd.img-*
echo '### Selected GRUB entries'
grep -E '^[[:space:]]*(menuentry|linux|initrd)' /boot/grub/grub.cfg
sync
systemd-run --on-active=5s --unit=ventuno-os-reboot /usr/bin/systemctl reboot
