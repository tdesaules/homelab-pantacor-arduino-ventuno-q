#!/usr/bin/env python3
"""Exercise explicit native update phases; preserve intent before each command."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from local_updates import Session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('bundle', type=Path)
parser.add_argument('--phase', choices=('stage', 'upgrade', 'downgrade', 'fault'), required=True)
args = parser.parse_args()
bundle = args.bundle.resolve()
manifest = json.loads((bundle / 'manifest.json').read_text())
evidence = bundle / ('evidence-' + args.phase)
evidence.mkdir(mode=0o700, exist_ok=False)
session = Session('192.168.1.20', 2222, evidence)

def revision(): return session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')

def wait(target, core_version, statuses, timeout=300):
    until = time.monotonic() + timeout
    last = None
    while time.monotonic() < until:
        try:
            active = revision()
            progress = json.loads(session.control('steps', 'show-progress', target))
            (evidence / 'progress.json').write_text(json.dumps(progress, indent=2))
            if active == target and progress['status'] in statuses:
                core = json.loads(session.run('cat /etc/ventuno-core-release'))
                node = json.loads(session.run('kubectl get node ventuno-k0s -o json --request-timeout=10s'))
                baseline_node = json.loads((bundle / 'evidence-stage/node.json').read_text())
                assert node['metadata']['uid'] == baseline_node['metadata']['uid']
                health = session.run('cat /trial-status/health.status')
                guard = dict(line.split('=', 1) for line in session.run('cat /trial-status/guard.status').splitlines())
                if progress['status'] == 'DONE' and int(guard['elapsed']) < 130:
                    time.sleep(3)
                    continue
                if core['version'] == core_version and 'ready=1' in health and any(
                        x['type'] == 'Ready' and x['status'] == 'True' for x in node['status']['conditions']):
                    with urllib.request.urlopen('http://192.168.1.20:30080/hello', timeout=5) as response: api = json.load(response)
                    assert api['message'] == 'Hello world'
                    state = json.loads(session.control('steps', 'get', 'current'))
                    expected = json.loads((bundle / ('base.json' if target == manifest['base'] else 'upgrade.json')).read_text())
                    assert state == expected
                    result = {'revision': active, 'progress': progress, 'core': core, 'nodeUID': node['metadata']['uid'],
                              'cmdline': session.run('cat /proc/cmdline'), 'api': api}
                    (evidence / 'result.json').write_text(json.dumps(result, indent=2))
                    return result
        except (RuntimeError, ValueError, AssertionError, OSError, subprocess.TimeoutExpired) as error:
            last = repr(error)
        time.sleep(3)
    raise RuntimeError(f'Phase {args.phase} did not reach {target}: {last}; evidence: {evidence}')

if args.phase == 'stage':
    assert revision() == manifest['base']
    (evidence / 'node.json').write_text(session.run('kubectl get node ventuno-k0s -o json'))
    existing = {x['name'] for x in json.loads(session.control('steps', 'ls'))}
    assert not {manifest['upgrade'], manifest['fault']} & existing
    for path in sorted((bundle / 'objects').iterdir()):
        with path.open('rb') as stream: assert hashlib.file_digest(stream, 'sha256').hexdigest() == path.name
        remote = '/tmp/native-update-' + path.name
        session.upload(path, remote)
        session.control('objects', 'put', remote, path.name)
        session.run('rm ' + remote)
    for kind in ('upgrade', 'fault'):
        remote = '/tmp/native-update-' + kind + '.json'
        session.upload(bundle / (kind + '.json'), remote)
        session.control('steps', 'put', remote, manifest[kind])
    (evidence / 'steps.json').write_text(session.control('steps', 'ls'))
    print('PASS: candidate images and states staged; no activation')
else:
    expected = manifest['upgrade'] if args.phase == 'downgrade' else manifest['base']
    assert revision() == expected
    target = manifest['fault'] if args.phase == 'fault' else manifest['base'] if args.phase == 'downgrade' else manifest['upgrade']
    command = 'pvcontrol cmd ' + ('run ' if args.phase == 'upgrade' else 'run-commit ') + target
    (evidence / 'intent.json').write_text(json.dumps({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'previous': expected, 'target': target, 'command': command}, indent=2))
    session.reboot_command(command)
    if args.phase == 'upgrade':
        wait(target, '0.8.1', ('UPDATED', 'DONE'))
        session.reboot()
        result = wait(target, '0.8.1', ('DONE',))
        assert 'pv_rev=' + target in result['cmdline'].split()
        (evidence / 'boot-state.txt').write_text(session.run('cat /boot-state/grubenv /boot-state/boot-budget'))
    elif args.phase == 'downgrade':
        result = wait(target, '0.8.0', ('DONE',))
        assert 'pv_rev=' + target in result['cmdline'].split()
    else:
        # Do not mistake the old revision still serving the request for rollback.
        time.sleep(70)
        result = wait(manifest['base'], '0.8.0', ('DONE',), timeout=300)
        progress = json.loads(session.control('steps', 'show-progress', target))
        (evidence / 'failed-progress.json').write_text(json.dumps(progress, indent=2))
        log = session.run('cat /pantavisor/logs/' + target + '/pantavisor/pantavisor.log', timeout=30)
        (evidence / 'failed-boot.log').write_text(log)
        assert progress['status'] == 'ERROR', progress
        assert "platform 'core' status is now STARTED" in log
        assert "platform 'core' status is now READY" not in log
    print('PASS:', args.phase, '; evidence:', evidence)
