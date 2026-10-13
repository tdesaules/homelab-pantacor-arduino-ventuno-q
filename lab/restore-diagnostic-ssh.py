#!/usr/bin/env python3
"""Restore interactive core access after the diagnostic readiness registration race."""
import json
import subprocess
import time
from diagnostic_ssh import ROOT
from local_updates import Session
from runtime_validation import container_status, host_pid1_ready, section

directory = ROOT / 'artifacts/autonomous/6491b61ba229489cb8bacb1719de7c2c'
inputs = json.loads((directory / 'build-inputs.json').read_text())
session = Session('192.168.1.20', 2222, directory)
end = time.monotonic() + 330
restarts = 0
last_restart = -100
stopped = False
last_error = ''
while time.monotonic() < end:
    try:
        text = session.snapshot('ssh-recovery-status')
        assert host_pid1_ready(text)
        core = container_status(text, 'core')
        app = container_status(text)
        guard = dict(line.split('=', 1) for line in section(text, '### Host PID 1').split('\n### ', 1)[0].splitlines() if '=' in line)
        elapsed = int(guard['elapsed'])
        if core['status'] != 'READY':
            time.sleep(2); continue
        if app['status'] != 'READY' and not stopped and elapsed >= 40:
            if restarts < 2 and elapsed - last_restart >= 15:
                session.control('containers', 'restart', 'diagnostic')
                restarts += 1
                last_restart = elapsed
                print(f'Requested diagnostic restart {restarts} at {elapsed}s', flush=True)
            elif restarts == 2 and elapsed >= 90:
                session.control('containers', 'stop', 'diagnostic')
                stopped = True
                print('Diagnostic explicitly stopped to preserve core SSH access', flush=True)
        health = dict(line.split('=', 1) for line in section(text, '### Host health').splitlines() if '=' in line)
        if elapsed >= 215 and health.get('ready') == '1' and (app['status'] == 'READY' or (stopped and app['status'] == 'STOPPED')):
            session.shells(inputs)
            result = {'elapsed': elapsed, 'core': core['status'], 'diagnostic': app['status'],
                      'diagnostic_restarts': restarts, 'diagnostic_stopped': stopped, 'interactive_ssh': True}
            (directory / 'ssh-recovery-result.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result, indent=2))
            break
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, AssertionError) as error:
        last_error = str(error)
    time.sleep(3)
else:
    raise SystemExit('Interactive SSH recovery not confirmed: ' + last_error)
