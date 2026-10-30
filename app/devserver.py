"""เปิดหน้าจอในเบราว์เซอร์ (ไว้ใช้บนเครื่อง DEV / ทดสอบ) — python -m app.devserver [port]

หน้าจอเรียก /api/<ชื่อเมธอด> แทน window.pywebview.api
"""
from __future__ import annotations

import json
import logging
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .api import Api
from .store import Store

log = logging.getLogger(__name__)


class Handler(SimpleHTTPRequestHandler):
    api: Api = None

    def log_message(self, fmt, *args):  # เงียบ
        pass

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        name = self.path[5:]
        if name.startswith("_") or not hasattr(self.api, name):
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        args = json.loads(self.rfile.read(n) or b"[]")
        try:
            out = getattr(self.api, name)(*args)
            body, code = json.dumps(out, ensure_ascii=False).encode("utf-8"), 200
        except Exception as e:  # noqa: BLE001
            log.exception("api %s", name)
            body, code = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"), 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 8765, open_browser: bool = True):
    logging.basicConfig(level=logging.INFO)
    store = Store(config.data_dir() / "data.db")
    Handler.api = Api(store)
    ui = config.resource_dir() / "ui"
    srv = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ui)))
    url = f"http://127.0.0.1:{port}/index.html"
    print("ตรวจบิล (dev) →", url, "| ข้อมูล:", config.data_dir())
    if open_browser:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765, open_browser="--no-browser" not in sys.argv)
