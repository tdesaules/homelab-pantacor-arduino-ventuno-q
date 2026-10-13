"""Exercise autonomous reboots without Ubuntu or host-side store copies between them."""
import json
import subprocess
import time
from local_updates import Session, decode, update_ready
from runtime_validation import container_status, section


def fields(text, heading):
    return dict(line.split('=', 1) for line in section(text, heading).split('\n### ', 1)[0].splitlines() if '=' in line)


def wait_boot(session, install_id, previous=None, timeout=180, is_alive=None):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if is_alive and not is_alive(): raise RuntimeError('Guest exited before the next SSH boot')
        try:
            text = session.run('cat /proc/cmdline; cat /proc/sys/kernel/random/boot_id', timeout=8)
            boot_id = text.splitlines()[-1]
            if 'ventuno_install=' + install_id in text and boot_id != previous:
                return boot_id
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(2)
    raise RuntimeError('Autonomous boot did not become reachable over SSH')


def exercise_autonomous(host, port, directory, inputs, output, install_id, is_alive=None, expected_identity=None, previous_starts=None, require_watchdog=False):
    session = Session(host, port, directory)
    boots = [wait_boot(session, install_id, is_alive=is_alive)]
    scenario = session.exercise(inputs, output, install_id, expected_identity)
    if previous_starts is not None: assert scenario['initial_starts'] == previous_starts + 1
    boots.append(wait_boot(session, install_id, boots[-1], is_alive=is_alive))
    session.wait_ready('autonomous-committed', inputs, scenario['last_good_revision'], '2.0.0',
                       scenario['expected_after_commit_boot'], scenario['application_identity'], core_starts=2, require_done=True)
    # Deliberately exceed the former 180s runtime deadline with a healthy core.
    until = time.monotonic() + 240
    while time.monotonic() < until:
        text = session.snapshot('autonomous-unbounded')
        guard = fields(text, '### Host PID 1')
        health = fields(text, '### Host health')
        assert guard['phase'] == 'autonomous' and guard['return_after'] == '0' and guard['supervisor_version'] == '5'
        if require_watchdog: assert guard['watchdog'] == 'armed' and guard['watchdog_timeout'] == '30'
        assert update_ready(text, inputs, scenario['last_good_revision'], '2.0.0', scenario['expected_after_commit_boot'], scenario['application_identity'], core_starts=2)
        assert health['ready'] == '1'
        if int(guard['elapsed']) >= 205: break
        time.sleep(10)
    else: raise RuntimeError('Unbounded operation was not observed')
    print('PASS: autonomous operation beyond 180 seconds, with fresh runtime health', flush=True)
    session.fail_after_commit(inputs, scenario, reboot_trial=True)
    boots.append(wait_boot(session, install_id, boots[-1], is_alive=is_alive))
    until = time.monotonic() + 25
    while time.monotonic() < until:
        try:
            text = session.snapshot('autonomous-unready-boot')
            _, heartbeat_text = section(text, '### Persistent application data').split('\n', 1)
            heartbeat, _ = json.JSONDecoder().raw_decode(heartbeat_text)
            if heartbeat['application_version'] == '2.0.0-unready':
                assert heartbeat['starts'] == scenario['expected_after_commit_boot'] + 1
                assert heartbeat['identity'] == scenario['application_identity']
                assert container_status(text)['status'] != 'READY'
                assert 'pv_rev=locals/app-unready' in session.run('cat /proc/cmdline').split()
                break
        except (RuntimeError, ValueError, KeyError, IndexError):
            pass
        time.sleep(1)
    else: raise RuntimeError('Failed try-boot was not observed')
    boots.append(wait_boot(session, install_id, boots[-1], is_alive=is_alive))
    session.wait_ready('autonomous-rollback', inputs, scenario['last_good_revision'], '2.0.0',
                       scenario['expected_after_rollback_boot'], scenario['application_identity'], core_starts=4, require_done=True)
    progress = json.loads(session.control('steps', 'show-progress', scenario['failed_revision']))
    assert progress['status'] == 'ERROR' and 'goal' in progress['status-msg'].lower()
    session.shells(inputs)
    result = scenario | {'install_id': install_id, 'core_boot_ids': boots, 'core_starts': 4, 'failed_progress': progress}
    (directory / 'autonomous-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: GRUB selected the try revision once, then restored the committed revision automatically', flush=True)
    session.reboot_command('ventuno-reboot ubuntu')
    return result
