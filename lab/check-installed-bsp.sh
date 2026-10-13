#!/usr/bin/env bash
set -eu
echo '### Installed-package verification against local dpkg metadata'
dpkg --verify "linux-image-$(uname -r)" "linux-modules-$(uname -r)" linux-firmware-dragonwing
echo '### Kernel and module checksums'
sha256sum "/boot/vmlinuz-$(uname -r)" "/boot/config-$(uname -r)"
for m in nvme ath11k_pci dwmac_qcom_ethqos overlay; do
    sha256sum "$(modinfo -n "$m")"
done
