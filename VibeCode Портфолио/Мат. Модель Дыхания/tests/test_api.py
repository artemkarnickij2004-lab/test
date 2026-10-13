import csv
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Handler, ThreadingHTTPServer


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)

    def request(self,route,body=None):
        request=Request(self.url+route,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers={"Content-Type":"application/json"})
        return urlopen(request,timeout=3)

    def new_session(self):
        with self.request("/api/session",{}) as response:
            return json.load(response)

    def test_html_and_health(self):
        with self.request("/") as response:
            html=response.read().decode()
            self.assertIn('id="oxygen-input"',html)
            self.assertIn("Начать дыхание",html)
        with self.request("/api/health") as response:
            self.assertEqual(json.load(response)["engine"],"Python")

    def test_independent_sessions(self):
        a,b=self.new_session(),self.new_session()
        self.assertNotEqual(a["session"],b["session"])
        with self.request("/api/start",{"session":a["session"],"oxygen_percent":15}) as response:
            self.assertEqual(json.load(response)["status"],"running")
        with self.request("/api/state?session="+b["session"]) as response:
            self.assertEqual(json.load(response)["status"],"idle")

    def test_controls_and_csv(self):
        token=self.new_session()["session"]
        for route,expected in [("start","running"),("pause","paused"),("resume","running"),("pause","paused")]:
            with self.request("/api/"+route,{"session":token,"oxygen_percent":"20,9"}) as response:
                state=json.load(response)
                self.assertEqual(state["status"],expected)
                self.assertEqual(state["oxygen_percent"],20.9)
        with self.request("/api/report.csv?session="+token) as response:
            data=response.read()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            rows=list(csv.reader(io.StringIO(data.decode("utf-8-sig")),delimiter=";"))
            self.assertEqual(len(rows[0]),7)
            self.assertGreaterEqual(len(rows),2)
        with self.request("/api/reset",{"session":token}) as response:
            state=json.load(response)
            self.assertEqual(state["status"],"idle")
            self.assertEqual(state["inspired_total_ml"],0)

    def test_invalid_requests(self):
        token=self.new_session()["session"]
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/start",{"session":token,"oxygen_percent":101})
        self.assertEqual(ctx.exception.code,400)
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/state?session=not-a-real-session")
        self.assertEqual(ctx.exception.code,400)
        with self.assertRaises(HTTPError) as ctx:
            self.request("/not-a-page")
        self.assertEqual(ctx.exception.code,404)


if __name__=="__main__":unittest.main()
