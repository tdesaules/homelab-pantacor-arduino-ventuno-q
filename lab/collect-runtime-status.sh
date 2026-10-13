#!/bin/sh
# Workstation-driven diagnostics using native tools; not installed in core.
set -eu
echo '### Pantavisor containers'
containers=$(pvcontrol containers ls)
printf '%s\n' "$containers"
echo '### Running revision'
cat /pantavisor/device-meta/pantavisor.revision
printf '\n### Current revision\n'
pvcontrol steps get current
echo '### Revision progress'
pvcontrol steps show-progress current
if printf '%s\n' "$containers" | grep -q '"name":"diagnostic"'; then
    echo '### Persistent application data'
    cat /diagnostic-data/boots /diagnostic-data/heartbeat.json
fi
echo '### Core'
printf 'CORE_STARTS='
cat /data/boots
cat /run/ventuno-dhcp.state
echo 'NETWORK_OWNER=core'
cat /proc/1/comm
echo '### Core release'
cat /etc/ventuno-core-release
echo '### Host PID 1'
cat /trial-status/guard.status
echo '### Application storage'
cat /trial-status/app-storage.status
echo '### Host health'
cat /trial-status/health.status
echo '### Clock synchronization'
cat /run/ventuno-time.status
