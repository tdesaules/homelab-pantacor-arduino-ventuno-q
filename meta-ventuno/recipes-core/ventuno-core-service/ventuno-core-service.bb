SUMMARY = "Core DHCP, SSH and local Pantavisor administration"
LICENSE = "MIT"
require conf/ventuno-core.inc
PV = "${VENTUNO_CORE_VERSION}"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
FILESEXTRAPATHS:prepend := "${THISDIR}/../ventuno-trial-guard/files:"
SRC_URI = "file://ventuno-network file://udhcpc.script file://ventuno-core-service file://ventuno-time"
S = "${WORKDIR}"
RDEPENDS:${PN} = "busybox dropbear-pv pantavisor-pvcontrol lxc6-pv"

do_install() {
    install -d ${D}${libdir}/ventuno ${D}${sysconfdir}/dropbear \
        ${D}/home/root/.ssh ${D}/data ${D}/pantavisor \
        ${D}/proc ${D}/sys ${D}/dev/pts ${D}/run ${D}/tmp
    install -d ${D}${libexecdir}/ventuno
    install -m 0755 ${WORKDIR}/ventuno-network ${D}${libexecdir}/ventuno/network
    install -m 0755 ${WORKDIR}/ventuno-core-service ${D}${libexecdir}/ventuno/core-init
    install -m 0755 ${WORKDIR}/ventuno-time ${D}${libexecdir}/ventuno/time-sync
    install -m 0755 ${WORKDIR}/udhcpc.script ${D}${libdir}/ventuno/
    touch ${D}${sysconfdir}/ventuno-revision-network
    printf '/bin/sh\n/bin/bash\n/usr/bin/bash\n' > ${D}${sysconfdir}/shells
    chmod 0700 ${D}/home/root ${D}/home/root/.ssh
    chmod 1777 ${D}/tmp
}
FILES:${PN} += "${libdir}/ventuno /home/root /data /pantavisor /proc /sys /dev /run /tmp"

do_install[postfuncs] += "write_core_release"
python write_core_release() {
    import hashlib
    import json
    from pathlib import Path
    source = Path(d.getVar('WORKDIR'))
    names = ('ventuno-network', 'udhcpc.script', 'ventuno-core-service', 'ventuno-time')
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}
    release = {
        'name': 'ventuno-core', 'version': d.getVar('PV'),
        'build_system': 'yocto', 'service_sources': hashes,
        'shells': {'bash': '5.3.20'},
        'admin_interface': 'native',
        'service_sources_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
    }
    if d.getVar('VENTUNO_KUBERNETES_TOOLS') == '1':
        release['kubernetes_tools'] = {'kubectl': '1.36.4', 'k0sctl': '0.33.1', 'k9s': '0.51.0'}
    (Path(d.getVar('D')) / 'etc/ventuno-core-release').write_text(json.dumps(release, sort_keys=True, indent=2) + '\n')
}
