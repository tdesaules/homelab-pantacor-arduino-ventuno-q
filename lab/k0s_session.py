"""Qualify the Kubernetes POC from the workstation, retaining private access locally."""
import json
import http.client
import subprocess
import time
import urllib.request
from local_updates import Session
from persistent_session import wait_boot

IMAGE = 'docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e'


def exercise_k0s(host, port, api_port, web_port, directory, inputs, install_id, is_alive=None,
                 expected_revision='0', return_ubuntu=True, pressure_test=False):
    directory.chmod(0o700)
    session = Session(host, port, directory)
    boot = wait_boot(session, install_id, timeout=240, is_alive=is_alive)
    (directory / 'cgroups.log').write_text(session.run('cat /proc/self/cgroup; cat /proc/mounts; ls /sys/fs/cgroup'))
    assert session.run('cat /sys/fs/cgroup/memory.max').strip() == str(inputs['core_image'].get('memory_limit', 268435456))
    assert 'memory' in session.run('cat /sys/fs/cgroup/cgroup.controllers')
    config = directory / 'kubeconfig'
    until = time.monotonic() + 600
    while time.monotonic() < until:
        if is_alive and not is_alive(): raise RuntimeError('Guest exited during k0s bootstrap')
        try:
            status = session.run('cat /k0s-access/status; cat /k0s-access/sysinfo.log; cat /k0s-access/service.log', timeout=15)
            (directory / 'k0s-bootstrap.log').write_text(status)
            if 'phase=failed' in status: raise ValueError('k0s preflight/process failed; see k0s-bootstrap.log')
            text = session.run('cat /k0s-access/admin.conf', timeout=10)
            if 'client-key-data:' in text:
                import re
                text = re.sub(r'https://[^\s]+:6443', f'https://{host}:{api_port}', text)
                config.touch(mode=0o600)
                config.write_text(text)
                break
        except (RuntimeError, subprocess.TimeoutExpired): pass
        time.sleep(5)
    else: raise RuntimeError('k0s did not publish its kubeconfig')
    epoch = int(session.run('date +%s').strip())
    assert abs(epoch - time.time()) < 60, 'Board clock is not synchronized with UTC'
    (directory / 'clock.log').write_text(session.run('date -u; cat /run/ventuno-time.status'))

    def kubectl(*args, timeout=180, data=None, diagnose=True):
        result = subprocess.run(['kubectl', '--kubeconfig', str(config), '--request-timeout=30s', *args],
                                input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        if result.returncode and diagnose:
            for name, command in [('pods-describe.txt', ['describe', 'pods', '-A']),
                                  ('kube-router.log', ['logs', '-n', 'kube-system', 'ds/kube-router', '--all-containers']),
                                  ('kube-proxy.log', ['logs', '-n', 'kube-system', 'ds/kube-proxy', '--all-containers'])]:
                try:
                    report = subprocess.run(['kubectl', '--kubeconfig', str(config), '--request-timeout=15s', *command],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
                    (directory / name).write_text(report.stdout)
                except subprocess.TimeoutExpired:
                    (directory / name).write_text('Diagnostic request timed out\n')
        if result.returncode: raise RuntimeError(result.stdout)
        return result.stdout

    def ready():
        until = time.monotonic() + 600
        while time.monotonic() < until:
            try:
                text = kubectl('get', 'nodes', '-o', 'json', diagnose=False)
                (directory / 'nodes.json').write_text(text)
                nodes = json.loads(text)['items']
                if nodes and all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in n['status']['conditions']) for n in nodes): return
                log = session.run('cat /k0s-access/service.log', timeout=30)
                if log.count('failed to run Kubelet:') >= 3 or sum('Mount failed:' in line and 'executable file not found' in line for line in log.splitlines()) >= 3:
                    (directory / 'k0s-failed.log').write_text(log)
                    raise ValueError('Kubelet repeatedly failed; see k0s-failed.log')
            except (RuntimeError, subprocess.TimeoutExpired): pass
            time.sleep(10)
        (directory / 'pods-failed.txt').write_text(kubectl('get', 'pods', '-A', '-o', 'wide'))
        (directory / 'k0s-failed.log').write_text(session.run('cat /k0s-access/service.log', timeout=30))
        raise RuntimeError('Kubernetes node did not become Ready')

    ready()
    print('PASS: cgroup v2 and Kubernetes node Ready', flush=True)
    if inputs.get('resource_policy'):
        from resource_policy import validate_node_budget
        node = json.loads(kubectl('get', 'node', 'ventuno-k0s', '-o', 'json'))
        configuration = json.loads(kubectl('get', '--raw', '/api/v1/nodes/ventuno-k0s/proxy/configz'))
        resources = dict(line.split('=', 1) for line in session.run('cat /k0s-access/resources.status').splitlines())
        budget = validate_node_budget(node, configuration, resources)
        (directory / 'resources.json').write_text(json.dumps(budget, indent=2) + '\n')
    progress = json.loads(session.control('steps', 'show-progress', 'current'))
    assert progress['status'] == 'DONE'
    revision = session.run('cat /pantavisor/device-meta/pantavisor.revision').strip().strip('"')
    assert revision == expected_revision
    kubectl('wait', '--for=condition=Ready', 'pods', '--all', '-n', 'kube-system', '--timeout=300s', timeout=330)
    security = {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}
    pod = {'metadata': {'labels': {'app': 'ventuno-poc'}}, 'spec': {
        'securityContext': {'runAsUser': 65532, 'runAsGroup': 65532, 'fsGroup': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'initContainers': [{'name': 'volume-owner', 'image': IMAGE, 'command': ['chown', '65532:65532', '/data'],
                            'securityContext': security | {'runAsUser': 0, 'capabilities': {'drop': ['ALL'], 'add': ['CHOWN']}},
                            'volumeMounts': [{'name': 'data', 'mountPath': '/data'}]}],
        'containers': [{'name': 'web', 'image': IMAGE, 'securityContext': security,
                        'command': ['sh', '-ec', 'test -s /data/identity || cat /proc/sys/kernel/random/uuid > /data/identity; ln -sf /data/identity /www/index.html; exec httpd -f -p 8080 -h /www'],
                        'ports': [{'containerPort': 8080}],
                        'readinessProbe': {'httpGet': {'path': '/', 'port': 8080}},
                        'resources': {'requests': {'cpu': '10m', 'memory': '8Mi'}, 'limits': {'cpu': '100m', 'memory': '32Mi'}},
                        'volumeMounts': [{'name': 'data', 'mountPath': '/data'}, {'name': 'www', 'mountPath': '/www'}]}],
        'volumes': [{'name': 'data', 'hostPath': {'path': '/data/poc', 'type': 'DirectoryOrCreate'}}, {'name': 'www', 'emptyDir': {}}],
    }}
    manifest = {'apiVersion': 'v1', 'kind': 'List', 'items': [
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'ventuno-poc'}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'web', 'namespace': 'ventuno-poc'},
         'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'ventuno-poc'}}, 'template': pod}},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'web', 'namespace': 'ventuno-poc'},
         'spec': {'type': 'NodePort', 'selector': {'app': 'ventuno-poc'}, 'ports': [{'port': 80, 'targetPort': 8080, 'nodePort': 30080}]}},
    ]}
    (directory / 'workload.json').write_text(json.dumps(manifest, indent=2) + '\n')
    kubectl('apply', '-f', '-', data=json.dumps(manifest))
    kubectl('rollout', 'status', 'deployment/web', '-n', 'ventuno-poc', '--timeout=240s', timeout=270)
    def identity():
        until = time.monotonic() + 180
        while time.monotonic() < until:
            try:
                with urllib.request.urlopen(f'http://{host}:{web_port}/', timeout=10) as response:
                    return response.read().decode().strip()
            except (OSError, http.client.HTTPException): time.sleep(3)
        raise RuntimeError('NodePort did not become reachable')
    before = identity()
    import uuid
    uuid.UUID(before)
    dns = kubectl('exec', '-n', 'ventuno-poc', 'deployment/web', '--', 'nslookup', 'kubernetes.default.svc.cluster.local')
    (directory / 'dns.txt').write_text(dns)
    print('PASS: system pods, NodePort and cluster DNS; rebooting', flush=True)
    session.reboot()
    wait_boot(session, install_id, boot, timeout=240, is_alive=is_alive)
    ready()
    kubectl('rollout', 'status', 'deployment/web', '-n', 'ventuno-poc', '--timeout=240s', timeout=270)
    assert identity() == before
    session.shells(inputs)
    if inputs['core_image']['release'].get('admin_interface') == 'native':
        from pathlib import Path
        kubectl('apply', '-k', str(Path(__file__).resolve().parents[1] / 'examples/hello-api'))
        kubectl('rollout', 'status', 'deployment/web', '-n', 'ventuno-poc', '--timeout=240s', timeout=270)
        until = time.monotonic() + 45
        while time.monotonic() < until:
            try:
                if json.loads(identity()) == {'message': 'Hello world', 'service': 'hello-api'}: break
            except ValueError: pass
            time.sleep(2)
        else: raise RuntimeError('Python API did not replace the previous NodePort response')
        print('PASS: Python REST API Hello world', flush=True)
    if inputs['core_image']['release'].get('kubernetes_tools'):
        from management_tools_session import exercise_management_tools
        exercise_management_tools(session)
    containers = json.loads(session.control('containers', 'ls'))
    assert {item['name']: item['status'] for item in containers} == {'core': 'READY', 'k0s': 'STARTED'}
    (directory / 'runtime.log').write_text(session.snapshot('runtime'))
    result = {'revision': revision, 'core_starts': int(session.run('cat /data/boots').strip()),
              'k0s': inputs['k0s'], 'workload_identity': before, 'node_ready': True, 'dns': True,
              'api_port': api_port, 'web_port': web_port, 'app_storage': session.run('cat /trial-status/app-storage.status')}
    (directory / 'pods.txt').write_text(kubectl('get', 'pods', '-A', '-o', 'wide'))
    (directory / 'pods.json').write_text(kubectl('get', 'pods', '-A', '-o', 'json'))
    if pressure_test:
        # Fault injection is enabled only by the QEMU caller, never on hardware.
        import uuid
        name = 'memory-probe-' + uuid.uuid4().hex[:12]
        allocation_mib = budget['allocatable_bytes'] // (1024 * 1024) + 128
        assert allocation_mib < 2048, 'Pressure test is restricted to the small VM budget'
        probe = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': 'ventuno-poc'},
                 'spec': {'restartPolicy': 'Never', 'activeDeadlineSeconds': 150,
                          'containers': [{'name': 'probe',
                              'image': 'docker.io/library/python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83',
                              'command': ['python', '-c', 'import time\nbuffer=bytearray(' + str(allocation_mib) + '*1024*1024)\nfor offset in range(0,len(buffer),4096): buffer[offset]=1\ntime.sleep(120)'],
                              'resources': {'requests': {'memory': '16Mi', 'cpu': '10m'},
                                            'limits': {'memory': str(allocation_mib + 64) + 'Mi', 'cpu': '500m'}}}]}}
        kubectl('create', '-f', '-', data=json.dumps(probe))
        try:
            until = time.monotonic() + 150
            while time.monotonic() < until:
                observed = json.loads(kubectl('get', 'pod', name, '-n', 'ventuno-poc', '-o', 'json'))
                if observed['status'].get('reason') == 'Evicted': break
                time.sleep(3)
            else: raise RuntimeError('Expected memory eviction was not observed in QEMU')
            (directory / 'memory-eviction.json').write_text(json.dumps(observed, indent=2) + '\n')
            assert json.loads(session.control('containers', 'ls'))[0]['status'] == 'READY'
            assert json.loads(identity())['message'] == 'Hello world'
            print('PASS: QEMU memory pressure evicts the probe; core, API and workload stay available', flush=True)
        finally:
            kubectl('delete', 'pod', name, '-n', 'ventuno-poc', '--ignore-not-found', '--wait=false')
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    if return_ubuntu: session.reboot('ubuntu')
    return result
