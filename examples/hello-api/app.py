"""A dependency-free REST API used only to exercise the k0s-ready OS."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, *, allow=None):
        body = json.dumps(payload, separators=(',', ':')).encode() + b'\n'
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        if allow: self.send_header('Allow', allow)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/hello'):
            self.respond(200, {'message': 'Hello world', 'service': 'hello-api'})
        elif path == '/healthz':
            self.respond(200, {'status': 'ok'})
        else:
            self.respond(404, {'error': 'not found'})

    def do_POST(self):
        self.respond(405, {'error': 'method not allowed'}, allow='GET')


if __name__ == '__main__':
    with ThreadingHTTPServer(('0.0.0.0', 8080), Handler) as server:
        server.serve_forever()
