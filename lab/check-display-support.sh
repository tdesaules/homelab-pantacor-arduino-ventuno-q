#!/usr/bin/env bash
set -eu
uname -r
echo '### Framebuffers and DRM connectors'
for f in /sys/class/graphics/fb*/name /sys/class/drm/card*-*/status; do
    if test -f "$f"; then printf '%s: ' "$f"; cat "$f"; fi
done
echo '### Kernel console options'
grep -E '^CONFIG_(VT|VT_CONSOLE|FRAMEBUFFER_CONSOLE|DRM_SIMPLEDRM|FB_EFI|SERIAL_AMBA_PL011|SERIAL_AMBA_PL011_CONSOLE|ARCH_VIRT|VIRTIO.*|DRM_MSM|DRM_FBDEV_EMULATION)=' "/boot/config-$(uname -r)"
echo '### Display modules and firmware declarations'
for module in msm adv7511 dispcc0_sa8775p gpucc_sa8775p phy_qcom_edp; do
    modinfo "$module" | grep -E '^(filename|firmware|depends):'
done
echo '### Relevant kernel messages'
journalctl -k -b --no-pager | grep -Ei 'drm|adreno|adv75|display|hdmi|dsi|gmu|framebuffer' || true
