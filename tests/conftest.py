import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIX = ROOT / "tests" / "fixtures"
PRIVATE = ROOT / "tests" / "private"


@pytest.fixture(scope="session", autouse=True)
def _fixtures():
    if not any(FIX.glob("*.xlsx")):
        from tests.make_fixtures import build
        build()


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """กันเทสต์เขียนไฟล์ลงเครื่องจริง (Desktop, Downloads, Documents\\ตรวจบิล, %LOCALAPPDATA%)"""
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("INVOICE_CHECKER_DATA", str(tmp_path / "_data"))
    monkeypatch.setenv("INVOICE_CHECKER_ARCHIVE", str(tmp_path / "_archive"))


def fixture_file(iv_no: str, contains: str = "") -> Path:
    for f in sorted(FIX.glob("*.xlsx")):
        if iv_no in f.name and contains in f.name:
            return f
    raise FileNotFoundError(iv_no)
