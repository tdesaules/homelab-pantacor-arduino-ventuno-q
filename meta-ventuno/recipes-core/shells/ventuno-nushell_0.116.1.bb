SUMMARY = "Official Nushell ARM64 musl release"
HOMEPAGE = "https://www.nushell.sh/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=ad705ee79cb73e3022613380a1696d2c"
SRC_URI = "https://github.com/nushell/nushell/releases/download/${PV}/nu-${PV}-aarch64-unknown-linux-musl.tar.gz"
SRC_URI[sha256sum] = "b103770c00bf322c409caa007aad44882d1cc5d24d82f719f877812ac33d6ad1"
S = "${WORKDIR}/nu-${PV}-aarch64-unknown-linux-musl"
COMPATIBLE_HOST = "aarch64.*-linux-musl"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped"
do_configure[noexec] = "1"
do_compile[noexec] = "1"
do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/nu ${D}${bindir}/nu
}
