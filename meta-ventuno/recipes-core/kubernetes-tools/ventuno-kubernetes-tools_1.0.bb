SUMMARY = "Pinned ARM64 Kubernetes administration clients"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"
SRC_URI = "https://dl.k8s.io/release/v1.36.4/bin/linux/arm64/kubectl;downloadfilename=kubectl-v1.36.4-arm64;name=kubectl;unpack=0 \
           https://github.com/k0sproject/k0sctl/releases/download/v0.33.1/k0sctl-linux-arm64;downloadfilename=k0sctl-v0.33.1-arm64;name=k0sctl;unpack=0 \
           https://github.com/derailed/k9s/releases/download/v0.51.0/k9s_Linux_arm64.tar.gz;downloadfilename=k9s-v0.51.0-arm64.tar.gz;name=k9s;subdir=k9s"
SRC_URI[kubectl.sha256sum] = "0ecf44450ee6063bf19dd166a103ee6df4a9034455c2abce626e6eea657d73fb"
SRC_URI[k0sctl.sha256sum] = "3632072361f3e83dde9b34f83eea49673d3bfe84763cf361edc3aec7209231a6"
SRC_URI[k9s.sha256sum] = "3ee05c82e5f9198928a4e86133608ba6a2c10a2244d6a7789e820f78319d640c"
S = "${WORKDIR}"
COMPATIBLE_HOST = "aarch64.*-linux"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped ldflags"
RDEPENDS:${PN} = "ca-certificates ncurses-terminfo-base"

do_install() {
    install -d ${D}${bindir} ${D}/home/root/.kube ${D}/home/root/.local
    install -m 0755 ${WORKDIR}/kubectl-v1.36.4-arm64 ${D}${bindir}/kubectl
    install -m 0755 ${WORKDIR}/k0sctl-v0.33.1-arm64 ${D}${bindir}/k0sctl
    install -m 0755 ${WORKDIR}/k9s/k9s ${D}${bindir}/k9s
    chmod 0700 ${D}/home/root/.kube
    ln -s /k0s-access/admin.conf ${D}/home/root/.kube/config
    ln -s /data/kube-cache ${D}/home/root/.kube/cache
    ln -s /data/config ${D}/home/root/.config
    ln -s /data/cache ${D}/home/root/.cache
    ln -s /data/state ${D}/home/root/.local/state
    ln -s /data/share ${D}/home/root/.local/share
}
FILES:${PN} += "/home/root"
