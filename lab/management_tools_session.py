"""Exercise clients and a maintenance shell from core, with real API/PTY traffic."""
import json
import re
import shlex
import subprocess
import time
from diagnostic_ssh import ssh_command


def exercise_management_tools(session):
    version = session.run('kubectl version --client -o json; k0sctl version; k9s version')
    (session.directory / 'management-versions.log').write_text(version)
    assert all(value in version for value in ('v1.36.4', '0.33.1', '0.51.0'))
    assert session.run('readlink /home/root/.kube/config').strip() == '/k0s-access/admin.conf'
    nodes = json.loads(session.run('kubectl get nodes -o json --request-timeout=30s'))
    assert any(node['metadata']['name'] == 'ventuno-k0s' for node in nodes['items'])
    legacy = session.run('if command -v ventuno-enter >/dev/null 2>&1; then echo yes; else echo no; fi').strip() == 'yes'
    if not legacy:
        native_entry(session)
    else:
        legacy_entry(session)

    command = 'export TERM=xterm-256color; stty rows 35 cols 120; timeout 25 k9s --readonly --headless --command nodes --logFile /tmp/k9s-management-test.log'
    args = ssh_command(session.host, session.port, command=command)
    args.insert(1, '-tt')
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(12)
        screen, _ = process.communicate(b':q\r', timeout=25)
    finally:
        if process.poll() is None: process.kill(); process.wait()
    (session.directory / 'k9s-screen.log').write_bytes(screen)
    assert process.returncode == 0, screen.decode(errors='replace')
    assert b'ventuno-k0s' in screen, 'k9s did not render the local node'
    (session.directory / 'management-result.json').write_text(json.dumps({
        'local_clients': True, 'shared_kubeconfig': True, 'k9s_tui': True,
        'k0s_shell': True, 'native_administration': not legacy}, indent=2) + '\n')
    print('PASS: core clients, k9s TUI and k0s maintenance shell', flush=True)


def native_entry(session):
    absent = session.run('for name in ventuno-enter ventuno-reboot ventuno-revision-status ventuno-core-service ventuno-network ventuno-time; do '
                         'if command -v "$name" >/dev/null 2>&1; then exit 1; fi; done; echo NATIVE_ONLY')
    assert 'NATIVE_ONLY' in absent
    command = ['kubectl', '-n', 'kube-system', 'debug', 'node/ventuno-k0s', '-it', '--profile=sysadmin',
               '--image=docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e',
               '--', 'nsenter', '-t', '1', '-m', '-u', '-i', '-n', '-p', '-r', '-w', '--', '/bin/sh', '-c',
               'set -e; test -t 0; test -t 1; command -v k0s; k0s kubectl get nodes -o name; '
               'printf "NODE_MEMORY_MAX="; cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.events; '
               'printf "POD_MEMORY_MAX="; cat /sys/fs/cgroup/kubepods/memory.max']
    text = session.run('stty rows 35 cols 120; ' + shlex.join(command), tty=True, timeout=150)
    (session.directory / 'k0s-shell.log').write_text(text)
    match = re.search(r'Creating debugging pod ([a-z0-9-]+)', text)
    assert match, text
    # A short command may write before kubectl has attached. The pod log is
    # authoritative for the complete output, including that initial interval.
    text += session.run('kubectl -n kube-system logs ' + match.group(1) + ' -c debugger')
    (session.directory / 'k0s-shell.log').write_text(text)
    session.run('kubectl -n kube-system delete pod ' + match.group(1) + ' --wait=true --timeout=30s', timeout=45)
    assert '/usr/bin/k0s' in text and 'node/ventuno-k0s' in text
    node_max = int(re.search(r'NODE_MEMORY_MAX=(\d+)', text)[1])
    pod_max = int(re.search(r'POD_MEMORY_MAX=(\d+)', text)[1])
    assert node_max - pod_max >= 1024 ** 3 - 1024 ** 2, 'Control-plane memory must remain outside the pod cgroup budget'


def legacy_entry(session):
    inside = session.run('ventuno-enter k0s sh -c ' + shlex.quote(
        'printf "NODE_SHELL="; cat /proc/1/comm; command -v k0s; '
        'test -r /var/lib/k0s/pki/admin.conf; k0s kubectl get nodes -o name'), timeout=150)
    assert 'NODE_SHELL=init.lxc.static' in inside and '/usr/bin/k0s' in inside and 'node/ventuno-k0s' in inside
    (session.directory / 'k0s-shell.log').write_text(inside)
    command = shlex.join(['ventuno-enter', 'k0s', 'sh', '-c',
                         'read -r value; printf "input:%s\\narg:%s\\n" "$value" "$1"',
                         'sh', 'spaces ; $(not-a-command)'])
    transported = session.run(command, data=b'hello from core\n', timeout=150)
    assert 'input:hello from core' in transported and 'arg:spaces ; $(not-a-command)' in transported
    session.run('ventuno-enter k0s sh -c "exit 17"; result=$?; test "$result" -eq 17', timeout=150)
    tty = session.run('stty rows 35 cols 120; ventuno-enter k0s sh -c "test -t 0 && test -t 1 && echo K0S_TTY_OK"',
                      tty=True, timeout=150)
    assert 'K0S_TTY_OK' in tty

    for _ in range(20):
        pods = json.loads(session.run('kubectl -n kube-system get pods -l app.kubernetes.io/name=ventuno-admin-shell -o json'))
        if not pods['items']: break
        time.sleep(1)
    else: raise RuntimeError('Maintenance pods were not removed')
