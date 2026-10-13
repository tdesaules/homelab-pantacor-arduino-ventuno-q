#!/bin/sh
# Executed inside the independent rescue, after an orderly native shutdown.
set -eu
identity=${1:-}
case "$identity" in ''|*[!0-9a-f]*) exit 2 ;; esac
[ "${#identity}" -eq 32 ]
test -f /run/ventuno-recovery
test -f /etc/ventuno-native
command -v setsid
setsid /bin/sh -c 'echo SETSID_EXECUTED'
test "$(blkid -s UUID -o value /dev/mmcblk0p71)" = e5defb48-4df4-40fc-8f97-7d635b46fcb8
test "$(blkid -s UUID -o value /dev/nvme0n1p1)" = 5ccb2c2f-c0f7-44a1-a291-b261a7d060a3
if grep -E ' /mnt/pv-system |^/dev/(mmcblk|nvme)' /proc/mounts; then exit 3; fi
e2fsck -f -n /dev/mmcblk0p71
e2fsck -f -n /dev/nvme0n1p1
mkdir -p /mnt/pv-system
mount -t ext4 -o ro,noload /dev/mmcblk0p71 /mnt/pv-system
test "$(cat /mnt/pv-system/boot/pantavisor/install-id)" = "$identity"
e2fsck -f -n /mnt/pv-system/boot/pantavisor/pvstore.ext4
grep '^ventuno_recovery=1' /mnt/pv-system/boot/pantavisor/state/boot-budget
umount /mnt/pv-system
mount -t ext4 /dev/mmcblk0p71 /mnt/pv-system
/usr/sbin/ventuno-bootctl stable
grep '^ventuno_recovery=0' /mnt/pv-system/boot/pantavisor/state/boot-budget
sync
umount /mnt/pv-system
echo 'PASS: setsid, clean filesystems and native boot rearmed; reboot is separate.'
