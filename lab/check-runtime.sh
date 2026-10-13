#!/usr/bin/env bash
# Temporary files and private mounts only; no partition or boot changes.
set -eu
if [ "$(id -u)" -ne 0 ]; then echo 'Run with --sudo'; exit 1; fi
echo '### Boot and security'
mokutil --sb-state
grep -E 'menuentry |linux |initrd |devicetree|chainloader' /boot/grub/grub.cfg
find /boot/efi/EFI -maxdepth 3 -type f -printf '%P\n'
echo '### GPT'
sfdisk --dump /dev/mmcblk0
echo '### NVMe signatures (read only)'
wipefs -n /dev/nvme0n1
echo '### Kernel module dependencies'
for m in nvme ath11k_pci stmmac dwmac_qcom_ethqos overlay dm_verity dm_crypt; do
    modinfo "$m" | grep -E '^(filename|firmware|depends|name):' || true
done
echo '### Package origins'
apt-cache policy "linux-image-$(uname -r)" linux-firmware-dragonwing
echo '### Ethernet connectivity'
gateway=$(ip -4 route show default dev end0 | awk 'NR==1 {print $3}')
ping -I end0 -c 5 -W 2 "$gateway"
echo '### Wi-Fi scan (no association)'
nmcli -f CHAN,FREQ,SIGNAL,SECURITY device wifi list ifname wlp3s0 --rescan yes
echo '### Available container images'
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}'
echo '### Namespace/storage smoke tests'
unshare --mount --pid --fork --net --uts --ipc --mount-proc bash -se <<'INNER'
mount --make-rprivate /
work=$(mktemp -d /var/tmp/pantavisor-check.XXXXXX)
cleanup() {
    mountpoint -q "$work/merged" && umount "$work/merged"
    mountpoint -q "$work/squash" && umount "$work/squash"
    rm -rf "$work"
}
trap cleanup EXIT
mkdir "$work"/{source,squash,upper,work,merged}
printf 'pantavisor-smoke-test\n' > "$work/source/marker"
mksquashfs "$work/source" "$work/root.squashfs" -comp zstd -noappend -processors 2 -quiet
mount -t squashfs -o loop,ro "$work/root.squashfs" "$work/squash"
cmp "$work/source/marker" "$work/squash/marker"
mount -t overlay overlay -o "lowerdir=$work/squash,upperdir=$work/upper,workdir=$work/work" "$work/merged"
printf 'overlay-write\n' > "$work/merged/new"
test -f "$work/upper/new"
test ! -e "$work/squash/new"
ip link add pvtest0 type veth peer name pvtest1
ip link del pvtest0
echo 'PASS: namespaces, veth, loop, squashfs-zstd, overlayfs'
python3 - "$work" <<'PY'
import hashlib, os, pathlib, sys, time
p = pathlib.Path(sys.argv[1]) / 'emmc-test.bin'
data = os.urandom(1024 * 1024)
expected = hashlib.sha256(data * 64).hexdigest()
start = time.monotonic()
with p.open('wb') as f:
    for _ in range(64):
        f.write(data)
    f.flush()
    os.fsync(f.fileno())
with p.open('rb') as f:
    os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    actual = hashlib.file_digest(f, 'sha256').hexdigest()
assert actual == expected
print('PASS: eMMC 64 MiB write/fsync/read/checksum;', round(time.monotonic()-start, 2), 's')
PY
INNER
echo '### NVMe 256 MiB direct read'
dd if=/dev/nvme0n1 of=/dev/null bs=4M count=64 iflag=direct status=progress
echo '### Device mapper targets'
modprobe dm_verity
modprobe dm_crypt
dmsetup targets
echo '### Current kernel errors'
journalctl -k --since '5 minutes ago' -p err --no-pager
