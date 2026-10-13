#!/usr/bin/env bash
# Run independently of SSH so package/service restarts cannot interrupt dpkg.
set -euo pipefail
test "$(id -u)" -eq 0
work=$(mktemp -d /var/tmp/ventuno-os-update.XXXXXX)
dpkg-query -W '-f=${Package}\t${Version}\n' > "$work/packages-before.tsv"
apt-mark showhold > "$work/held-before.txt"
cat > "$work/run.sh" <<'WORKER'
#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
date -u
apt-get -y --no-remove -o DPkg::Lock::Timeout=300 \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold dist-upgrade
echo 'APT_UPGRADE_COMPLETE'
snap refresh
echo 'SNAP_REFRESH_COMPLETE'
dpkg --audit
apt-get check
apt-get --simulate dist-upgrade
snap refresh --list
if test -f /var/run/reboot-required; then
    cat /var/run/reboot-required /var/run/reboot-required.pkgs
fi
date -u
echo 'OS_UPDATE_COMPLETE'
WORKER
chmod 700 "$work/run.sh"
systemd-run --no-block --unit=ventuno-os-update --description='Ubuntu and Arduino lab updates' \
    --property=Type=oneshot --property=RemainAfterExit=yes \
    --property=TimeoutStartSec=2h \
    --property=StandardOutput=append:/var/log/ventuno-os-update.log \
    --property=StandardError=append:/var/log/ventuno-os-update.log \
    /bin/bash "$work/run.sh"
printf 'Worker and pre-update inventory: %s\nLog: /var/log/ventuno-os-update.log\n' "$work"
