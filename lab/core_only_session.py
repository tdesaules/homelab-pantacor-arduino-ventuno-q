"""Qualify decommissioning without deleting the retired application's data."""
import json
import time
from core_only import core_only_ready
from local_updates import Session
from persistent_session import wait_boot


def wait_core(session, release, name):
    until = time.monotonic() + 100
    while time.monotonic() < until:
        try:
            text = session.snapshot(name)
            if core_only_ready(text, 'locals/core-only-040', release): return text
        except RuntimeError: pass
        time.sleep(2)
    raise RuntimeError('Core-only did not become DONE/READY')


def exercise_core_only(host, port, directory, inputs, bundle, install_id, is_alive=None):
    session = Session(host, port, directory)
    boot = wait_boot(session, install_id, is_alive=is_alive)
    for _ in range(25):
        try:
            before = {name: session.run('cat /diagnostic-data/' + name).strip() for name in ('boots', 'identity', 'heartbeat.json')}
            if before['heartbeat.json']: break
        except RuntimeError: pass
        time.sleep(1)
    else: raise RuntimeError('Initial diagnostic data not available')
    session.control('containers', 'stop', 'diagnostic')
    for _ in range(15):
        app = next(item for item in json.loads(session.control('containers', 'ls')) if item['name'] == 'diagnostic')
        if app['status'] == 'STOPPED': break
        time.sleep(1)
    else: raise RuntimeError('Diagnostic did not stop')
    before = {name: session.run('cat /diagnostic-data/' + name).strip() for name in ('boots', 'identity', 'heartbeat.json')}
    release = json.loads((bundle / 'release.json').read_text())
    for path in (bundle / 'objects').iterdir():
        remote = '/tmp/core-only-' + path.name
        session.upload(path, remote)
        session.control('objects', 'put', remote, path.name)
    session.upload(bundle / 'state.json', '/tmp/core-only.json')
    session.control('steps', 'put', '/tmp/core-only.json', 'locals/core-only-040')
    session.reboot_command('ventuno-revision-status control cmd run-commit locals/core-only-040')
    boot = wait_boot(session, install_id, boot, is_alive=is_alive)
    wait_core(session, release, 'core-only-first')
    session.shells({'core_image': {'release': release}})
    assert session.run('test ! -e /diagnostic-data && echo DETACHED').strip() == 'DETACHED'
    session.reboot_command('ventuno-reboot')
    wait_boot(session, install_id, boot, is_alive=is_alive)
    wait_core(session, release, 'core-only-rebooted')
    until = time.monotonic() + 220
    while time.monotonic() < until:
        text = wait_core(session, release, 'core-only-stable')
        from runtime_validation import section
        fields = dict(line.split('=', 1) for line in section(text, '### Host PID 1').split('\n### ', 1)[0].splitlines() if '=' in line)
        if int(fields['elapsed']) >= 205: break
        time.sleep(10)
    else: raise RuntimeError('Core-only stability window not reached')
    result = {'revision': 'locals/core-only-040', 'core_starts': 3,
              'application_identity': before['identity'], 'retained_data': before}
    (directory / 'core-only-result.json').write_text(json.dumps(result, indent=2) + '\n')
    session.reboot_command('ventuno-reboot ubuntu')
    print('PASS: core-only rebooted and stayed healthy; Bash present, Nushell absent', flush=True)
    return result
