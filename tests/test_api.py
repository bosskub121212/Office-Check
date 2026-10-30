import base64
import zipfile

import openpyxl

from app.api import Api, initials, short_name
from app.store import Store
from tests.conftest import FIX, fixture_file


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
    assert s["kpi"]["sub"] == "55,495.33"
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


def test_commit_can_skip_files(tmp_path):
    api = Api(Store(tmp_path / "data.db"))
    files = [fixture for fixture in sorted(FIX.glob("*.xlsx"))][:3]
    res = api.analyze(payload(files))
    out = api.commit(res["token"], [1])
    assert out["saved"] == 2
    names = {r["filename"] for r in api._store.file_rows()}
    assert files[1].name not in names and files[0].name in names


def test_summary_alerts_duplicate_number_other_company(tmp_path):
    api = Api(Store(tmp_path / "data.db"))
    res = api.analyze(payload(sorted(FIX.glob("*.xlsx"))))
    api.commit(res["token"])
    alerts = api.summary("2026-02")["alerts"]
    assert [a["iv"] for a in alerts] == ["NNCIV-269003"]


def test_stored_files_are_reparsed_after_reader_upgrade(tmp_path):
    """ไฟล์ที่นำเข้าด้วยตัวอ่านเวอร์ชันเก่า (ผลอ่านผิด) ต้องถูกอ่านใหม่จากสำเนาที่เก็บไว้"""
    from app.reader import read_file
    st = Store(tmp_path / "data.db")
    f = fixture_file("269002")
    pf = read_file(f)
    pf.iv.vat_included = False          # จำลองผลอ่านผิดจากเวอร์ชันเก่า
    pf.iv.date = None
    st.add_file(pf, f.read_bytes())
    api = Api(st)                         # เปิดโปรแกรมเวอร์ชันใหม่
    fixed = st.files()[0][2]
    assert fixed.iv.vat_included and fixed.iv.date is not None
    assert st.get_setting("parser_version")
    assert list((tmp_path / "backups").glob("*before-reparse*"))
    assert api._reparse_if_needed() == 0  # ครั้งต่อไปไม่ต้องอ่านซ้ำ
