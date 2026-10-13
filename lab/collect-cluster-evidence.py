#!/usr/bin/env python3
"""Capture current health without treating Kubernetes object age as host uptime."""
import datetime
import json
from pathlib import Path
import subprocess
import uuid
from local_updates import Session

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / 'artifacts/cluster-audit' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, directory)
commands = {
    'core.txt': 'date -u; cat /proc/uptime; cat /trial-status/guard.status; cat /proc/meminfo; cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.events; df -h /data /k0s-access; cat /proc/mounts',
    'nodes.json': 'kubectl get nodes -o json',
    'pods.json': 'kubectl get pods -A -o json',
    'events.json': 'kubectl get events -A -o json',
    'kubelet-config.json': 'kubectl get --raw /api/v1/nodes/ventuno-k0s/proxy/configz',
    'node-stats.json': 'kubectl get --raw /api/v1/nodes/ventuno-k0s/proxy/stats/summary',
    'temperatures.txt': 'for zone in /sys/class/thermal/thermal_zone*; do [ -r "$zone/temp" ] || continue; printf "%s " "$zone"; cat "$zone/type" "$zone/temp"; done',
}
for name, command in commands.items(): (directory / name).write_text(session.run(command, timeout=60))
node = session.run('if command -v ventuno-enter >/dev/null 2>&1; then ventuno-enter k0s sh -c '
                   + "'cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.events; df -h /var/lib/k0s /data /var/log; ls /var/lib/k0s/db'"
                   + '; else cat /k0s-access/resources.status; fi', timeout=150)
(directory / 'k0s.txt').write_text(node)
(directory / 'captured.json').write_text(json.dumps({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2) + '\n')
print('Evidence:', directory)
