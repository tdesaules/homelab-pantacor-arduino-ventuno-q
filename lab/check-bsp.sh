#!/usr/bin/env bash
set -eu
echo '### BSP package download metadata'
apt-cache show linux-image-6.8.0-1078-qcom linux-modules-6.8.0-1078-qcom linux-firmware-dragonwing | grep -E '^(Package|Version|Source|Filename|SHA256):'
echo '### Required boot drivers'
grep -E '^CONFIG_(EFI.*|BLK_DEV_INITRD|RD_.*|MMC.*|SCSI|BLK_DEV_SD|BLK_DEV_NVME|PCIE_QCOM|PHY_QCOM.*|QCOM_SCM|QCOM_RPM.*|QCOM_SMEM|QCOM_SMP2P|QCOM_SYSMON|SERIAL_MSM.*|STMMAC.*|DWMAC_QCOM.*|ATH11K.*|WATCHDOG.*|QCOM_WDT|USB_XHCI.*|USB_DWC3.*|FW_LOADER.*)=' /boot/config-$(uname -r)
echo '### Active device tree'
sha256sum /sys/firmware/fdt
echo '### Boot artifact hashes'
sha256sum /boot/vmlinuz-$(uname -r) /boot/initrd.img-$(uname -r) /boot/config-$(uname -r) /boot/efi/EFI/ubuntu/*.efi
echo '### Loaded modules'
lsmod
echo '### Wi-Fi firmware files'
find -L /lib/firmware/ath11k/WCN6855 -maxdepth 3 -type f -printf '%P\n'
echo '### Watchdog identity (no opening the watchdog)'
for f in identity state timeout nowayout bootstatus; do
    printf '%s: ' "$f"
    cat "/sys/class/watchdog/watchdog0/$f"
done
echo '### Initrd driver entries'
lsinitramfs /boot/initrd.img-$(uname -r) | grep -E '(/mmc/|/sdhci[^/]*|/nvme/|/qcom/|/firmware/|/stmmac/)' || true
echo '### Cleanup verification'
find /var/tmp -maxdepth 1 \( -name 'pantavisor-check.*' -o -name 'pv-nvme-original-*' \) -print
losetup -l
systemctl --failed --no-pager
