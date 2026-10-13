import importlib.util
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

path = Path(__file__).resolve().parents[1] / 'examples/hello-api/app.py'
spec = importlib.util.spec_from_file_location('hello_api', path)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class HelloApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_json_and_health(self):
        with urllib.request.urlopen(self.url + '/hello?test=1') as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), 'application/json')
            self.assertEqual(json.load(response), {'message': 'Hello world', 'service': 'hello-api'})
        with urllib.request.urlopen(self.url + '/healthz') as response:
            self.assertEqual(json.load(response), {'status': 'ok'})

    def test_missing_route_and_unsupported_method(self):
        for request, status in [(self.url + '/missing', 404),
                                (urllib.request.Request(self.url + '/hello', method='POST'), 405)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, status)
            self.assertIn('error', json.load(error.exception))
            error.exception.close()
