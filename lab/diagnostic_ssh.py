"""SSH arguments for the lab's separately pinned diagnostic host identity."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ROOT / 'artifacts/diagnostic-ssh'
COMMAND = "printf 'SSH_DIAGNOSTIC_OK\\n'; id; uname -r; cat /proc/1/comm /proc/cmdline /run/ventuno-dhcp.state; ip -4 address show"


def ssh_command(host, port=2222, identity=None, command=COMMAND):
    return ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
            '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
            '-o', 'PreferredAuthentications=publickey',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=ventuno-diagnostic',
            '-o', 'UserKnownHostsFile=' + str(KEYS / 'known_hosts'),
            '-o', 'GlobalKnownHostsFile=/dev/null', '-i', str(identity or KEYS / 'client_ed25519'),
            '-p', str(port), 'root@' + host, command]
