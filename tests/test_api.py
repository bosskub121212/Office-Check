import base64
import zipfile

import openpyxl

from app.api import Api, initials, short_name
from app.store import Store
from tests.conftest import FIX


def payload(paths):
    return [{"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode()} for p in paths]


def test_short_name_and_initials():
    assert short_name("บริษัท ไก่ทอง (ประเทศไทย) จำกัด (สำนักงานใหญ่)") == "ไก่ทอง (ประเทศไทย)"
    assert initials("บริษัท ดีมาก เทคโนโลยี จำกัด") == "ดี"
    assert initials("บริษัท ไก่ทอง จำกัด") == "ไก่"
    assert initials("Example Co., Ltd.") == "EX"


def test_import_flow_preview_then_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICE_CHECKER_DATA", str(tmp_path / "data"))
    api = Api(Store(tmp_path / "data.db"))
    files = sorted(FIX.glob("*.xlsx"))
    res = api.analyze(payload(files))
    assert res["new_count"] == len(files)
    by_iv = {}
    for r in res["results"]:
        by_iv.setdefault(r.get("iv"), []).append(r)
    assert any(r["dropped"] for r in by_iv["NNCIV-269001"])           # ไฟล์ copy ถูกบอกว่าจะทิ้ง
    assert api.bootstrap()["months"] == []                             # ยังไม่บันทึก
    out = api.commit(res["token"])
    assert out["saved"] == len(files) and out["month"] == "2026-03"

    # นำเข้าซ้ำ → ข้าม
    again = api.analyze(payload(files[:1]))
    assert again["results"][0]["status"] == "same" and again["new_count"] == 0
    api.cancel(again["token"])

    s = api.summary("2026-02")
    assert s["kpi"]["sub"] == "53,495.33"
    assert s["kpi"]["billed_count"] == 2
    pay = api.payables()
    assert pay["count"] == 3
    api.set_paid("NNCBI-260901", "2026-03-15")
    assert api.payables()["count"] == 2
    assert {r["iv"] for r in api.problems()["rows"]} >= {"NNCIV-269004", "NNCIV-269006", "NNCIV-269001"}

    ex = api.export("2026-02")
    assert ex["ok"]
    wb = openpyxl.load_workbook(ex["path"])
    assert "ต้องตรวจ" in wb.sheetnames

    rep = api.bug_report("ทดสอบ")
    names = zipfile.ZipFile(rep["path"]).namelist()
    assert "info.json" in names and any(n.startswith("files/") for n in names)


def test_bad_file_in_preview(tmp_path):
    api = Api(Store(tmp_path / "data.db"))
    res = api.analyze([{"name": "broken.xlsx", "b64": base64.b64encode(b"not excel").decode()}])
    assert res["results"][0]["level"] == "red"
