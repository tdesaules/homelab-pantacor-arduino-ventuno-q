SUMMARY = "Core connectivity and administration container for Pantavisor"
LICENSE = "MIT"
require conf/ventuno-core.inc
PV = "${VENTUNO_CORE_VERSION}"
inherit image

PACKAGE_INSTALL = "busybox base-passwd curl dropbear-pv pantavisor-pvcontrol lxc6-pv ventuno-core-service ventuno-bash ${@'ventuno-kubernetes-tools' if d.getVar('VENTUNO_KUBERNETES_TOOLS') == '1' else ''} ${ROOTFS_BOOTSTRAP_INSTALL}"
IMAGE_FEATURES = ""
IMAGE_LINGUAS = ""
IMAGE_FSTYPES = "squashfs"
IMAGE_NAME_SUFFIX = ""
IMAGE_ROOTFS_SIZE = "8192"
IMAGE_ROOTFS_EXTRA_SPACE = "0"
EXTRA_IMAGEDEPENDS = ""
KERNEL_DEPLOY_DEPEND = ""
NO_RECOMMENDATIONS = "1"
EXTRA_IMAGECMD:squashfs = "-comp zstd"

do_image[postfuncs] += "export_core_release"
export_core_release() {
    install -m 0644 ${IMAGE_ROOTFS}/etc/ventuno-core-release \
        ${IMGDEPLOYDIR}/${IMAGE_LINK_NAME}.core-release.json
}
