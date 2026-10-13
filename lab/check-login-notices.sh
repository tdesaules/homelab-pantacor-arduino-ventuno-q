#!/usr/bin/env bash
set -eu
for f in /run/motd.dynamic /etc/motd /etc/update-manager/release-upgrades; do
    if test -f "$f"; then
        printf '\n### %s\n' "$f"
        stat -c 'Modified: %y' "$f"
        cat "$f"
    fi
done
echo '### Fresh update notice'
sh /etc/update-motd.d/90-updates-available
echo '### Arduino package policy snippets'
grep -nE 'Prompt=|release-upgrades|apt-mark|firmware-dragonwing' \
    /var/lib/dpkg/info/arduino-ventunoq-config.postinst \
    /var/lib/dpkg/info/arduino-ventunoq.postinst || true
