"""จุดเริ่มโปรแกรม: เปิดหน้าต่างด้วย pywebview"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import config


def setup_logging():
    logs = config.data_dir() / "logs"
    logs.mkdir(exist_ok=True)
    h = RotatingFileHandler(logs / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)


def main():
    setup_logging()
    log = logging.getLogger("main")
    log.info("start %s v%s frozen=%s", config.APP_NAME, config.__version__, getattr(sys, "frozen", False))
    sys.excepthook = lambda t, v, tb: log.critical("crash", exc_info=(t, v, tb))

    import webview

    from .api import Api
    from .store import Store

    store = Store(config.data_dir() / "data.db")
    api = Api(store)
    index = config.resource_dir() / "ui" / "index.html"
    window = webview.create_window(
        f"{config.APP_TITLE} v{config.__version__}", url=index.as_uri(), js_api=api,
        width=1380, height=900, min_size=(1100, 700), background_color="#E6E3F2")
    api._window = window
    api._on_quit = window.destroy
    webview.start(debug="--debug" in sys.argv, private_mode=False)
    store.close()


if __name__ == "__main__":
    main()
