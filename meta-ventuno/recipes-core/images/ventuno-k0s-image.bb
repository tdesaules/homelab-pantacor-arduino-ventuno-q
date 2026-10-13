SUMMARY = "System container for the Ventuno k0s single-node POC"
LICENSE = "MIT"
inherit image
IMAGE_FSTYPES = "squashfs"
PACKAGE_INSTALL = "busybox base-passwd ca-certificates lxc6-pv ventuno-k0s util-linux-mount util-linux-umount util-linux-findmnt iproute2 iptables kmod ethtool conntrack-tools ${ROOTFS_BOOTSTRAP_INSTALL}"
IMAGE_NAME_SUFFIX = ""
IMAGE_ROOTFS_SIZE = "8192"
IMAGE_ROOTFS_EXTRA_SPACE = "0"
EXTRA_IMAGEDEPENDS = ""
KERNEL_DEPLOY_DEPEND = ""
NO_RECOMMENDATIONS = "1"
EXTRA_IMAGECMD:squashfs = "-comp zstd"
IMAGE_LINGUAS = ""
IMAGE_FEATURES = ""
ROOTFS_POSTPROCESS_COMMAND += "k0s_system_users; "
python k0s_system_users() {
    from pathlib import Path
    root = Path(d.getVar('IMAGE_ROOTFS'))
    passwd = root / 'etc/passwd'
    group = root / 'etc/group'
    entries = passwd.read_text().splitlines()
    for uid, name in enumerate(('kube-apiserver', 'kube-scheduler', 'etcd', 'konnectivity-server'), 2001):
        assert not any(line.split(':')[0] == name or line.split(':')[2] == str(uid) for line in entries)
        with passwd.open('a') as stream:
            stream.write(f'{name}:!:{uid}:{uid}::/var/lib/k0s:/bin/false\n')
        with group.open('a') as stream:
            stream.write(f'{name}:!:{uid}:\n')
}
