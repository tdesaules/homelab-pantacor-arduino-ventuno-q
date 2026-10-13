#!/usr/bin/env python3
"""Create lab SSH keys locally and capture this board's Ethernet identity."""
import argparse
import gzip
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from initramfs_archive import newc_members, resolve_member

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('initramfs', type=Path)
args = parser.parse_args()
directory = root / 'artifacts/diagnostic-ssh'
directory.mkdir(mode=0o700, exist_ok=True)
client = directory / 'client_ed25519'
if not client.exists():
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'ventuno-diagnostic-client', '-f', str(client)], check=True)
hostkey = directory / 'dropbear_ed25519_host_key'
entries = {name: (mode, data) for name, mode, data in newc_members(gzip.decompress(args.initramfs.read_bytes()))}
with tempfile.TemporaryDirectory(prefix='ventuno-keygen-') as temp:
    temp = Path(temp)
    for name in entries:
        parts = name.split('/')
        if (len(parts) == 2 and parts[0] == 'lib' or len(parts) == 3 and parts[:2] == ['usr', 'lib']) and '.so' in parts[-1]:
            data = entries[resolve_member(entries, name)][1]
            if data.startswith(b'\x7fELF'):
                target = temp / parts[-1]
                if target.exists() and target.read_bytes() != data:
                    raise ValueError(f'Conflicting runtime library: {name}')
                target.write_bytes(data)
    loader = temp / 'loader'
    loader.write_bytes(entries[resolve_member(entries, 'lib/ld-musl-aarch64.so.1')][1])
    loader.chmod(0o755)
    keygen = temp / 'dropbearkey'
    keygen.write_bytes(entries[resolve_member(entries, 'usr/sbin/dropbearkey')][1])
    keygen.chmod(0o755)
    command = ['qemu-aarch64', str(loader), '--library-path', str(temp), str(keygen)]
    if not hostkey.exists():
        subprocess.run(command + ['-t', 'ed25519', '-f', str(hostkey)], check=True, capture_output=True)
    public = subprocess.check_output(command + ['-y', '-f', str(hostkey)], text=True)
    host_public = next(line for line in public.splitlines() if line.startswith('ssh-ed25519 '))
hostkey.chmod(0o600)
(directory / 'host_ed25519.pub').write_text(host_public + '\n')
(directory / 'known_hosts').write_text('ventuno-diagnostic ' + ' '.join(host_public.split()[:2]) + '\n')
env = os.environ | {'SSH_ASKPASS': str(root / 'lab/ssh-askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
base = ['ssh', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=10',
        '-o', 'NumberOfPasswordPrompts=1', 'arduino@192.168.1.20']
mac = subprocess.check_output(base + ['cat /sys/class/net/end0/address'], env=env, text=True).strip()
assert re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac)
dhcp = subprocess.check_output(base + ["nmcli -f DHCP4.OPTION device show end0"], env=env, text=True)
client_id = re.search(r'dhcp_client_identifier = ([0-9a-f:]+)', dhcp)
assert client_id and client_id.group(1) == '01:' + mac, 'Unsupported DHCP identity; inspect before provisioning'
profile = {'ethernet_mac': mac, 'expected_ipv4': str(ipaddress.IPv4Address('192.168.1.20')),
           'ssh_port': 2222, 'client_public_key': client.with_suffix('.pub').read_text().strip(),
           'host_public_key': host_public, 'host_key_file': str(hostkey),
           'dhcp_client_id': client_id.group(1)}
(directory / 'network-profile.json').write_text(json.dumps(profile, indent=2) + '\n')
(directory / 'config').write_text(f'''Host ventuno-diagnostic
    HostName {profile['expected_ipv4']}
    Port 2222
    User root
    IdentityFile {client}
    IdentitiesOnly yes
    IdentityAgent none
    HostKeyAlias ventuno-diagnostic
    UserKnownHostsFile {directory / 'known_hosts'}
    GlobalKnownHostsFile /dev/null
    StrictHostKeyChecking yes
''')
print('Network profile:', directory / 'network-profile.json')
print('Ethernet MAC:', mac)
subprocess.run(['ssh-keygen', '-lf', str(directory / 'host_ed25519.pub')], check=True)
