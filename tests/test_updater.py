import io
import json

from app import updater


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_release(tag, asset="InvoiceChecker.exe"):
    body = {"tag_name": tag, "body": "แก้บั๊ก", "assets": [{"name": asset, "browser_download_url": "https://x/InvoiceChecker.exe", "size": 30_000_000}]}
    return lambda req, timeout=0: FakeResp(json.dumps(body).encode())


def test_newer_version_available(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_release("v1.0.10"))
    r = updater.check(current="1.0.9")
    assert r["available"] and r["latest"] == "1.0.10" and r["url"]


def test_same_version_not_available(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_release("v1.0.0"))
    assert not updater.check(current="1.0.0")["available"]


def test_release_without_exe(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_release("v2.0.0", asset="other.zip"))
    assert not updater.check(current="1.0.0")["available"]


def test_offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    r = updater.check(current="1.0.0")
    assert not r["available"] and r["error"]


def test_apply_refuses_when_not_frozen():
    assert updater.apply("https://x")["ok"] is False
