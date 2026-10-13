#!/usr/bin/env bash
set -eu
echo '### Generic firmware package'
apt-cache show linux-firmware=20240318.git3b128b60-0ubuntu2.27 | grep -E '^(Package|Version|Filename|SHA256):'
echo '### Installed Wi-Fi firmware ownership'
dpkg-query -S '/lib/firmware/ath11k/WCN6855/*' '/lib/firmware/updates/ath11k/WCN6855/*' || true
echo '### Firmware override paths'
find /lib/firmware/updates -maxdepth 3 -type d
