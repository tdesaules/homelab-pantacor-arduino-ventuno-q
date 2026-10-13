#!/usr/bin/env python3
"""Verify revision 0, restart its LXC container, and record persistent data."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from diagnostic_ssh import ROOT, ssh_command
from runtime_validation import is_ready, is_stopped, network_ready, core_ready, host_pid1_ready

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--trial-id', required=True)
parser.add_argument('--host', default='192.168.1.20')
parser.add_argument('--revision-network', action='store_true')
parser.add_argument('--core', action='store_true')
args = parser.parse_args()
revision_network = args.revision_network or args.core
component = 'core' if args.core else 'network'
status_command = 'ventuno-revision-status' if revision_network else 'ventuno-runtime-status'
assert re.fullmatch('[0-9a-f]{32}', args.trial_id)
directory = ROOT / 'artifacts/trials' / args.trial_id
directory.mkdir(parents=True, exist_ok=True)
inputs = json.loads((directory / 'build-inputs.json').read_text()) if args.core else None

def management_ready(text, starts):
    if args.core:
        return (core_ready(text, starts, inputs['core_image']['release'])
                and (not inputs.get('pid1_runtime') or host_pid1_ready(text)))
    return network_ready(text, starts)

def command(text):
    result = subprocess.run(ssh_command(args.host, command=text), capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout

assert 'ventuno_trial=' + args.trial_id in command('cat /proc/cmdline')
for name, expected in (('runtime-before', 1), ('runtime-restarted', 2)):
    for _ in range(20):
        try:
            text = command(status_command)
        except RuntimeError as error:
            (directory / (name + '.log')).write_text(str(error))
            time.sleep(1)
            continue
        (directory / (name + '.log')).write_text(text)
        if is_ready(text, expected) and (not revision_network or management_ready(text, expected)):
            print(text)
            break
        time.sleep(1)
    else:
        raise SystemExit('Runtime did not reach expected state')
    if expected == 1:
        if revision_network:
            try:
                text = command(status_command + ' restart ' + component)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                text = str(error)  # SSH itself belongs to the restarted container.
            (directory / 'network-restart-request.log').write_text(text)
            for _ in range(25):
                time.sleep(1)
                try:
                    text = command(status_command)
                except (RuntimeError, subprocess.TimeoutExpired):
                    continue
                (directory / 'network-restarted.log').write_text(text)
                if is_ready(text, 1) and management_ready(text, 2):
                    break
            else:
                raise SystemExit('Revision network did not recover')
            print('PASS: network READY after restart; SSH reconnected; application counter still 1')
        print(command(status_command + ' restart diagnostic'))
print(command(status_command + ' stop diagnostic'))
for _ in range(10):
    text = command(status_command)
    (directory / 'runtime-stopped.log').write_text(text)
    if is_stopped(text):
        print(text)
        break
    time.sleep(1)
else:
    raise SystemExit('Container failed to stop')
print('PASS: revision DONE, container READY, persistent starts 1 -> 2, container stopped')
