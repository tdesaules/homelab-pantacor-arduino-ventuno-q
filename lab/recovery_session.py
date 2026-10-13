"""Exercise core-only autonomous boots, including the recovery latch."""
import json
import time
from core_only import core_only_ready
from local_updates import Session
from persistent_session import wait_boot


def exercise_recovery(host, port, directory, inputs, install_id, is_alive=None, failed_core=False):
    session = Session(host, port, directory)
    boot = wait_boot(session, install_id, is_alive=is_alive)
    for cycle in range(2):
        until = time.monotonic() + 240
        while time.monotonic() < until:
            try:
                text = session.snapshot('core-only-' + str(cycle))
                if core_only_ready(text, '0', inputs['core_image']['release']):
                    guard = session.run('cat /trial-status/guard.status')
                    elapsed = int(dict(line.split('=', 1) for line in guard.splitlines())['elapsed'])
                    if elapsed >= 130: break
            except RuntimeError:
                pass
            time.sleep(5)
        else:
            raise RuntimeError('Core-only did not remain READY through stability window')
        session.shells(inputs)
        if failed_core:
            result = {'revision': '0', 'core_starts': int(session.run('cat /data/boots').strip()),
                      'app_storage': session.run('cat /trial-status/app-storage.status')}
            session.reboot_command('ventuno-revision-status control containers stop core')
            return result
        if cycle == 0:
            session.reboot()
            boot = wait_boot(session, install_id, boot, is_alive=is_alive)
    starts = int(session.run('cat /data/boots').strip())
    storage = session.run('cat /trial-status/app-storage.status')
    result = {'revision': '0', 'core_starts': starts, 'app_storage': storage}
    (directory / 'recovery-result.json').write_text(json.dumps(result, indent=2) + '\n')
    session.reboot('ubuntu')
    return result
