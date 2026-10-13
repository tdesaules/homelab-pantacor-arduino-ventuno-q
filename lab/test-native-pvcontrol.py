#!/usr/bin/env python3
"""Check native pvcontrol with real curl and concurrent Unix-socket requests."""
import concurrent.futures
import json
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
source = subprocess.check_output(['git', '-C', str(ROOT / 'artifacts/pantavisor'), 'show',
    '48c582334875dde17634973049885c7ab6049116:tools/pvcontrol'])
patch = ROOT / 'meta-ventuno/recipes-pv/pantavisor/files/0004-prefer-curl-for-pvcontrol.patch'

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        assert self.rfile.readline().split()[:2] == [b'GET', b'/containers']
        while self.rfile.readline() not in (b'\r\n', b'\n', b''): pass
        body = b'[{"name":"core","status":"READY"}]'
        self.wfile.write(b'HTTP/1.0 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)

with tempfile.TemporaryDirectory(prefix='pvcontrol-', dir='/tmp/opencode') as temporary:
    directory = Path(temporary)
    (directory / 'tools').mkdir()
    path = directory / 'tools/pvcontrol'
    path.write_bytes(source)
    subprocess.run(['git', 'apply', '--unsafe-paths', '--directory', str(directory), str(patch)], check=True)
    (directory / 'pvcurl').write_text('#!/bin/sh\nexit 99\n')
    (directory / 'pvcurl').chmod(0o755)
    env = os.environ | {'PATH': str(directory) + ':' + os.environ['PATH']}
    env.pop('CURL_CMD', None)
    socket = str(directory / 'api.sock')
    with socketserver.ThreadingUnixStreamServer(socket, Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(_):
            result = subprocess.run(['sh', str(path), '-s', socket, 'containers', 'ls'], env=env,
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == [{'name': 'core', 'status': 'READY'}]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(request, range(24)))
        override = subprocess.run(['sh', str(path), '-s', socket, 'containers', 'ls'],
                                  env=env | {'CURL_CMD': 'pvcurl'}, capture_output=True)
        assert override.returncode != 0
        server.shutdown()
print('PASS: native curl transport, 24 concurrent requests and explicit override')
