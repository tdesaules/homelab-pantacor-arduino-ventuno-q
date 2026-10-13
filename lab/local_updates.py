"""Pinned-SSH shell checks and native Pantavisor local application transitions."""
import json
from pathlib import Path
import shlex
import subprocess
import time
import uuid
from diagnostic_ssh import ssh_command
from runtime_validation import section, container_status, core_ready, host_pid1_ready


def decode(text, heading):
    return json.JSONDecoder().raw_decode(section(text, heading))[0]


def update_ready(text, inputs, revision, version, starts, identity, core_starts=1):
    try:
        _, data = section(text, '### Persistent application data').split('\n', 1)
        heartbeat, _ = json.JSONDecoder().raw_decode(data)
        running = section(text, '### Running revision').splitlines()[0].strip('"')
        progress = decode(text, '### Revision progress')
        return (running == revision and container_status(text)['status'] == 'READY'
                and progress['status'] in ('DONE', 'UPDATED')
                and core_ready(text, core_starts, inputs['core_image']['release']) and host_pid1_ready(text)
                and heartbeat['starts'] == starts and heartbeat['identity'] == identity
                and heartbeat['application_version'] == version)
    except (ValueError, KeyError, IndexError, StopIteration, TypeError):
        return False


class Session:
    def __init__(self, host, port, directory):
        self.host, self.port, self.directory = host, port, directory

    def run(self, command, data=None, timeout=20, tty=False):
        args = ssh_command(self.host, self.port, command=command)
        if tty: args.insert(1, '-tt')
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        text = result.stdout.decode(errors='replace')
        if result.returncode:
            raise RuntimeError(text + result.stderr.decode(errors='replace'))
        return text

    def control(self, *args):
        # Historical images use a lock around their minimal HTTP client.
        # Current images use native pvcontrol with curl's independent requests.
        return self.run('if command -v ventuno-revision-status >/dev/null 2>&1; then '
                        'ventuno-revision-status control ' + shlex.join(args) +
                        '; else pvcontrol ' + shlex.join(args) + '; fi')

    def reboot(self, target='pantavisor'):
        if target not in ('pantavisor', 'ubuntu'): raise ValueError('Unknown boot target')
        self.reboot_command("printf '%s\\n' " + target + ' > /boot-control/next; pvcontrol cmd reboot')

    def reboot_command(self, command):
        # Reboot can terminate the SSH server before its exit status reaches us.
        # The caller must subsequently verify a new boot/recovery, not retry it.
        try:
            self.run(command)
        except RuntimeError as error:
            if not any(message in str(error) for message in ('closed by remote host', 'Connection reset by peer', 'Broken pipe')):
                raise
            with (self.directory / 'reboot-transport.log').open('a') as log:
                log.write(command + '\n' + str(error) + '\n')

    def upload(self, path, remote):
        self.run('cat > ' + shlex.quote(remote), path.read_bytes())

    def snapshot(self, name):
        try:
            script = Path(__file__).with_name('collect-runtime-status.sh').read_bytes()
            text = self.run('if command -v ventuno-revision-status >/dev/null 2>&1; then '
                            'ventuno-revision-status; else sh -s; fi', data=script)
        except RuntimeError as error:
            (self.directory / (name + '.log')).write_text(str(error))
            raise
        (self.directory / (name + '.log')).write_text(text)
        return text

    def wait_ready(self, name, inputs, revision, version, starts, identity, core_starts=1, timeout=80, require_done=False):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                text = self.snapshot(name)
            except (RuntimeError, subprocess.TimeoutExpired):
                time.sleep(2)
                continue
            if (update_ready(text, inputs, revision, version, starts, identity, core_starts)
                    and (not require_done or decode(text, '### Revision progress')['status'] == 'DONE')):
                return text
            time.sleep(2)
        raise RuntimeError(f'{revision} did not reach stable {version}; inspect {name}.log')

    def shells(self, inputs):
        expected = inputs['core_image']['release']['shells']
        bash = self.run("bash --noprofile --norc -c 'printf \"%s\\n\" \"$BASH_VERSION\"'").strip()
        assert bash.startswith(expected['bash'] + '('), bash
        test = self.run("bash --noprofile --norc -c 'set -e; declare -A a=([core]=42); mapfile -t rows < <(printf \"a\\nb\\n\"); [[ ${a[core]} == 42 && ${#rows[@]} == 2 ]]; echo BASH_OK'")
        assert 'BASH_OK' in test
        assert 'BASH_TTY_OK' in self.run("bash --noprofile --norc -ic 'test -t 0 && echo BASH_TTY_OK'", tty=True)
        result = {'bash': bash, 'bash_arrays_process_substitution': True, 'ssh_pty': True}
        if 'nushell' in expected:
            # Historical core images still declare Nushell in their manifest.
            nu = self.run('nu --version').strip()
            assert nu == expected['nushell'], nu
            script = r'let x = ("{\"values\":[1,2,3]}" | from json | get values | math sum); if $x != 6 { error make {msg: "bad result"} }; print NU_OK'
            assert 'NU_OK' in self.run('nu --no-config-file -c ' + shlex.quote(script), timeout=30)
            assert 'NU_TTY_OK' in self.run("test -t 0 && nu --no-config-file -c 'print NU_TTY_OK'", tty=True, timeout=30)
            result.update(nushell=nu, nushell_json_pipeline=True)
        else:
            assert 'BASH_ONLY' in self.run('if command -v nu >/dev/null 2>&1; then echo UNEXPECTED_NUSHELL; else echo BASH_ONLY; fi')
            result['nushell_absent'] = True
        (self.directory / 'shell-check.json').write_text(json.dumps(result, indent=2) + '\n')
        print('PASS: declared shells, functional commands and SSH PTY', flush=True)

    def exercise(self, inputs, output, trial, expected_identity=None):
        token = 'ventuno_install=' if inputs.get('autonomous_boot') else 'ventuno_trial='
        assert token + trial in self.run('cat /proc/cmdline')
        for _ in range(25):
            try:
                text = self.snapshot('updates-initial')
                _, data = section(text, '### Persistent application data').split('\n', 1)
                heartbeat, _ = json.JSONDecoder().raw_decode(data)
                if update_ready(text, inputs, '0', '1.0.0', heartbeat['starts'], heartbeat['identity']): break
                time.sleep(1)
            except (RuntimeError, ValueError, KeyError, IndexError):
                time.sleep(1)
        else: raise RuntimeError('Initial application heartbeat not available')
        identity = str(uuid.UUID(heartbeat['identity']))
        if expected_identity: assert identity == expected_identity
        starts = heartbeat['starts']
        self.wait_ready('updates-initial', inputs, '0', '1.0.0', starts, identity)
        boot_id = self.run('cat /proc/sys/kernel/random/boot_id').strip()
        self.shells(inputs)
        bundle = output / 'local-revisions'
        revisions = json.loads((bundle / 'manifest.json').read_text())
        for path in sorted((bundle / 'objects').iterdir()):
            remote = '/tmp/ventuno-object-' + path.name
            self.upload(path, remote)
            self.control('objects', 'put', remote, path.name)
        for name, revision in revisions.items():
            remote = '/tmp/ventuno-' + name + '.json'
            self.upload(bundle / (name + '.json'), remote)
            self.control('steps', 'put', remote, revision['revision'])
        for offset, name in ((1, 'app-v2'), (2, 'app-v1'), (3, 'app-v2')):
            revision = revisions[name]
            self.control('cmd', 'run', revision['revision'])
            text = self.wait_ready(name + '-' + str(offset), inputs, revision['revision'], revision['application_version'], starts + offset, identity)
            assert decode(text, '### Current revision')['diagnostic/root.squashfs'] == revision['rootfs_sha256']
            assert self.run('cat /proc/sys/kernel/random/boot_id').strip() == boot_id
            print(f"PASS: {revision['revision']} stable; core uninterrupted; NVMe identity retained", flush=True)
            time.sleep(3)
        return self.complete_preparation(starts, identity, boot_id, revisions)

    def complete_preparation(self, starts, identity, boot_id, revisions):
        result = {'initial_starts': starts, 'expected_after_commit_boot': starts + 4,
                  'expected_after_rollback_boot': starts + 6, 'last_good_revision': revisions['app-v2']['revision'],
                  'application_identity': identity, 'core_boot_id': boot_id,
                  'failed_revision': revisions['app-unready']['revision']}
        (self.directory / 'updates-result.json').write_text(json.dumps(result, indent=2) + '\n')
        self.reboot_command('ventuno-revision-status control cmd reboot')
        print('Good revision UPDATED; native reboot requested before committing it on the next boot', flush=True)
        return result

    def finish_prepared(self, inputs, output):
        initial = (self.directory / 'updates-initial.log').read_text()
        _, data = section(initial, '### Persistent application data').split('\n', 1)
        heartbeat, _ = json.JSONDecoder().raw_decode(data)
        starts, identity = heartbeat['starts'], heartbeat['identity']
        assert update_ready(initial, inputs, '0', '1.0.0', starts, identity)
        revisions = json.loads((output / 'local-revisions/manifest.json').read_text())
        for offset, name in ((1, 'app-v2'), (2, 'app-v1')):
            saved = (self.directory / (name + '-' + str(offset) + '.log')).read_text()
            assert update_ready(saved, inputs, revisions[name]['revision'], revisions[name]['application_version'], starts + offset, identity)
        text = self.wait_ready('app-v2-3', inputs, revisions['app-v2']['revision'], '2.0.0', starts + 3, identity)
        assert decode(text, '### Current revision')['diagnostic/root.squashfs'] == revisions['app-v2']['rootfs_sha256']
        boot_id = self.run('cat /proc/sys/kernel/random/boot_id').strip()
        time.sleep(3)
        return self.complete_preparation(starts, identity, boot_id, revisions)

    def fail_after_commit(self, inputs, previous, reboot_trial=False):
        text = self.wait_ready('committed-revision', inputs, previous['last_good_revision'], '2.0.0',
                               previous['expected_after_commit_boot'], previous['application_identity'],
                               core_starts=2, require_done=True)
        print('PASS: updated revision reached DONE after reboot and is now the rollback point', flush=True)
        self.shells(inputs)
        time.sleep(3)
        (self.directory / 'updates-result.json').write_text(json.dumps(previous, indent=2) + '\n')
        if reboot_trial:
            self.reboot_command('ventuno-revision-status control cmd run-commit ' + shlex.quote(previous['failed_revision']))
            print('Unready revision queued for an actual bootloader try-boot', flush=True)
            return
        self.control('cmd', 'run', previous['failed_revision'])
        # Capture the failed application running but never announcing READY.
        until = time.monotonic() + 25
        while time.monotonic() < until:
            try:
                text = self.snapshot('app-unready-started')
                _, data = section(text, '### Persistent application data').split('\n', 1)
                bad, _ = json.JSONDecoder().raw_decode(data)
            except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError):
                time.sleep(1)
                continue
            if bad['application_version'] == '2.0.0-unready' and bad['starts'] == previous['expected_after_commit_boot'] + 1:
                assert bad['identity'] == previous['application_identity'] and container_status(text)['status'] != 'READY'
                break
            time.sleep(1)
        else: raise RuntimeError('The deliberately unready revision never started')
        print('Unready revision observed; waiting for native timeout/rollback reboot', flush=True)
