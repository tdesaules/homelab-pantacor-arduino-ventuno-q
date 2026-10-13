SUMMARY = "Minimal static LXC diagnostic rootfs for the first Pantavisor revision"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
SRC_URI = "file://diagnostic.c"
S = "${WORKDIR}"
DEPENDS = "squashfs-tools-native"
FILES:${PN} = "${datadir}/ventuno"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} -static -std=c11 -Wall -Wextra -Werror ${S}/diagnostic.c -o diagnostic
    ${CC} ${CFLAGS} ${LDFLAGS} -static -std=c11 -Wall -Wextra -Werror -DAPP_VERSION='"2.0.0"' ${S}/diagnostic.c -o diagnostic-v2
    ${CC} ${CFLAGS} ${LDFLAGS} -static -std=c11 -Wall -Wextra -Werror -DAPP_VERSION='"2.0.0-unready"' -DAPP_READY=0 ${S}/diagnostic.c -o diagnostic-unready
}

do_install() {
    install -d ${B}/container-root/dev ${B}/container-root/proc ${B}/container-root/sys \
        ${B}/container-root/tmp ${B}/container-root/run ${B}/container-root/data \
        ${B}/container-root/pantavisor ${D}${datadir}/ventuno
    for variant in diagnostic diagnostic-v2 diagnostic-unready; do
        install -m 0755 $variant ${B}/container-root/diagnostic
        env -u SOURCE_DATE_EPOCH mksquashfs ${B}/container-root ${D}${datadir}/ventuno/$variant.squashfs \
            -comp zstd -noappend -all-root -processors 2 -no-progress \
            -mkfs-time ${SOURCE_DATE_EPOCH} -all-time ${SOURCE_DATE_EPOCH}
    done
}
