SUMMARY = "Pinned ARM64 k0s single-node proof of concept"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"
SRC_URI = "https://github.com/k0sproject/k0s/releases/download/v1.36.4%2Bk0s.1/k0s-v1.36.4%2Bk0s.1-arm64;downloadfilename=k0s-v1.36.4-k0s.1-arm64;name=binary;unpack=0 \
           file://ventuno-k0s-service"
SRC_URI[binary.sha256sum] = "04f685c8c9c29262da64acf26fd928452f19d449ac58729592f686f915882319"
S = "${WORKDIR}"
COMPATIBLE_HOST = "aarch64.*-linux"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped ldflags"
do_install() {
    install -d ${D}${bindir} ${D}/var/lib/k0s ${D}/access ${D}/boot ${D}/run ${D}/etc/k0s ${D}/data
    install -d ${D}/proc ${D}/sys ${D}/dev/pts ${D}/tmp ${D}/pantavisor
    install -d ${D}/usr/libexec/kubernetes/kubelet-plugins/volume/exec
    install -m 0755 ${WORKDIR}/k0s-v1.36.4-k0s.1-arm64 ${D}${bindir}/k0s
    install -d ${D}${libexecdir}/ventuno
    install -m 0755 ${WORKDIR}/ventuno-k0s-service ${D}${libexecdir}/ventuno/k0s-init
}
FILES:${PN} += "/access /data /boot /run /var/lib/k0s /proc /sys /dev /tmp /pantavisor"
