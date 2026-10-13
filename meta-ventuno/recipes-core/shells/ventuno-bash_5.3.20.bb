SUMMARY = "GNU Bash 5.3 with upstream patches 001 through 020"
HOMEPAGE = "https://www.gnu.org/software/bash/"
LICENSE = "GPL-3.0-or-later"
LIC_FILES_CHKSUM = "file://COPYING;md5=d32239bcb673463ab874e80d47fae504"
SRC_URI = "https://ftp.gnu.org/gnu/bash/bash-5.3.tar.gz;name=source"
SRC_URI:append = " ${@' '.join('https://ftp.gnu.org/gnu/bash/bash-5.3-patches/bash53-%03d;name=p%03d;apply=yes;striplevel=0' % (n, n) for n in range(1, 21))}"
SRC_URI[source.sha256sum] = "0d5cd86965f869a26cf64f4b71be7b96f90a3ba8b3d74e27e8e9d9d5550f31ba"
SRC_URI[p001.sha256sum] = "1f608434364af86b9b45c8b0ea3fb3b165fb830d27697e6cdfc7ac17dee3287f"
SRC_URI[p002.sha256sum] = "e385548a00130765ec7938a56fbdca52447ab41fabc95a25f19ade527e282001"
SRC_URI[p003.sha256sum] = "f245d9c7dc3f5a20d84b53d249334747940936f09dc97e1dcb89fc3ab37d60ed"
SRC_URI[p004.sha256sum] = "9591d245045529f32f0812f94180b9d9ce9023f5a765c039b852e5dfc99747d0"
SRC_URI[p005.sha256sum] = "cca1ef52dbbf433bc98e33269b64b2c814028efe2538be1e2c9a377da90bc99d"
SRC_URI[p006.sha256sum] = "29119addefed8eff91ae37fd51822c31780ee30d4a28376e96002706c995ff10"
SRC_URI[p007.sha256sum] = "c0976bbfffa1453c7cfdd62058f206a318568ff2d690f5d4fa048793fa3eb299"
SRC_URI[p008.sha256sum] = "097cd723cbfb8907674ac32214063a3fd85282657ec5b4e544d2c0f719653fb4"
SRC_URI[p009.sha256sum] = "eee30fe78a4b0cb2fe20e010e00308899cfc613e0774ebb3c8557a1552f24f8c"
SRC_URI[p010.sha256sum] = "cf76f1cce2ea300c18bff9f002d21f280cc931acd17c28518110b93fe6e72569"
SRC_URI[p011.sha256sum] = "0298df8f5ea2a31d3be43ed7d269c5b3c7c342dd5b570bea7f64d66dcbbe7531"
SRC_URI[p012.sha256sum] = "d71379b39bebaedaf123414414e77fb458a0a43b9ad3116594c6df7ca6754573"
SRC_URI[p013.sha256sum] = "042f9cda967e24bf4211944697441e93d06ff42b4b998629a98a1b249279f200"
SRC_URI[p014.sha256sum] = "bd4360b401d38507e358783dcad8536a99c6789f0d3a5bd0cfb8c4a34144696c"
SRC_URI[p015.sha256sum] = "55b79ceee2fc27f6767eed697e939a7eb2fe2a28c01556bd75f18d581014f46e"
SRC_URI[p016.sha256sum] = "9ea29b266b7d24cb34d0ff3f1c4631e4d527bfe2d1ef15d17cdb924bf31ef767"
SRC_URI[p017.sha256sum] = "443b927b45c1558ca72052410f8b8f6e5152b617ed707061a2781d4375b0d1c3"
SRC_URI[p018.sha256sum] = "ae715d76c50341d7d7095e9a8d2eeed1ca9546152c2ac7289206f90cf30ac697"
SRC_URI[p019.sha256sum] = "a25c581e4d0057dea3833918438a930e2e86ee4c6dc17fe15267b7f04cbc4e3d"
SRC_URI[p020.sha256sum] = "df217ed3a9122aa2286d9b67bbe348661b6a9db262b580c29150dae55d532896"
S = "${WORKDIR}/bash-5.3"
DEPENDS = "ncurses bison-native"
inherit autotools-brokensep
EXTRA_OECONF = "--enable-job-control --without-bash-malloc --disable-nls bash_cv_wexitstatus_offset=8"
CFLAGS:append = " -std=gnu17"
BUILD_CFLAGS:append = " -std=gnu17"
RPROVIDES:${PN} = "bash"
RDEPENDS:${PN} += "ncurses-terminfo-base"

do_configure() {
    oe_runconf
}
do_compile() {
    rm -f ${B}/.build
    oe_runmake bash
}
do_install() {
    install -d ${D}${bindir} ${D}${base_bindir}
    install -m 0755 ${B}/bash ${D}${bindir}/bash
    if [ "${base_bindir}" != "${bindir}" ]; then
        ln -s ../usr/bin/bash ${D}${base_bindir}/bash
    fi
}
