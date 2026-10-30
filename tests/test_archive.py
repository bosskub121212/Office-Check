import base64
import sqlite3

from app import archive
from app.api import Api
from app.store import Store
from tests.conftest import FIX, fixture_file

FEB = "2569/02 กุมภาพันธ์ 2569"
MAR = "2569/03 มีนาคม 2569"


def make_api(tmp_path):
    api = Api(Store(tmp_path / "data.db"))
    api.choose_archive(str(tmp_path / "arc"))
    return api, tmp_path / "arc" / "ตรวจบิล"


def import_files(api, paths):
    res = api.analyze([{"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode()} for p in paths])
    return api.commit(res["token"])


def rel(root, p):
    return p.relative_to(root).as_posix()


def listing(root):
    return sorted(rel(root, p) for p in root.rglob("*.xlsx"))


def test_files_go_to_month_folders(tmp_path):
    api, root = make_api(tmp_path)
    out = import_files(api, sorted(FIX.glob("*.xlsx")))
    assert out["archive"]["ok"] and out["archive"]["copied"] == 9
    files = listing(root)
    assert f"{FEB}/ใบกำกับ NNCIV-269001-B901-R901_ลูกค้าเอ 3-2-69.xlsx" in files
    assert f"{FEB}/_ทิ้ง-เลขซ้ำ/ใบกำกับ NNCIV-269001_copy ลูกค้าเอ 20-2-69.xlsx" in files
    assert f"{MAR}/ใบกำกับ NNCIV-269007-B904_ลูกค้าเอ 2-3-69.xlsx" in files
    assert len(files) == 9
    # ทำซ้ำได้ ไม่สร้างไฟล์ซ้ำ
    again = api.sync_archive()
    assert again["copied"] == 0 and again["moved"] == 0 and again["unchanged"] == 9
    assert listing(root) == files


def test_copy_becomes_duplicate_and_moves(tmp_path):
    api, root = make_api(tmp_path)
    copy = fixture_file("269001", "copy")
    import_files(api, [copy])
    assert listing(root) == [f"{FEB}/{copy.name}"]                       # ตอนนี้ยังเป็นใบเดียว จึงมีผล
    import_files(api, [fixture_file("269001", "B901")])                  # ใบจริง (วันที่เก่ากว่า) มาทีหลัง
    files = listing(root)
    assert f"{FEB}/_ทิ้ง-เลขซ้ำ/{copy.name}" in files and f"{FEB}/{copy.name}" not in files


def test_remove_moves_to_removed_and_promotes_copy(tmp_path):
    api, root = make_api(tmp_path)
    orig, copy = fixture_file("269001", "B901"), fixture_file("269001", "copy")
    import_files(api, [orig, copy])
    rows = {r["filename"]: r["id"] for r in api._store.file_rows()}
    api.remove_file(rows[orig.name])
    files = listing(root)
    assert f"_ลบออกแล้ว/{orig.name}" in files
    assert f"{FEB}/{copy.name}" in files                                 # ใบ copy กลายเป็นใบที่มีผล


def test_same_name_different_content_gets_suffix(tmp_path):
    api, root = make_api(tmp_path)
    a = tmp_path / "x" / "บิล.xlsx"
    b = tmp_path / "y" / "บิล.xlsx"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(fixture_file("269002").read_bytes())
    b.write_bytes(fixture_file("269004").read_bytes())
    import_files(api, [a])
    import_files(api, [b])
    assert listing(root) == [f"{FEB}/บิล (2).xlsx", f"{FEB}/บิล.xlsx"]


def test_unreadable_folder(tmp_path):
    api, root = make_api(tmp_path)
    res = api.analyze([{"name": "เสีย.xlsx", "b64": base64.b64encode(b"not excel").decode()}])
    api.commit(res["token"])
    assert listing(root) == ["_อ่านไม่ได้/เสีย.xlsx"]


def test_change_folder_copies_everything(tmp_path):
    api, root = make_api(tmp_path)
    import_files(api, [fixture_file("269002")])
    out = api.choose_archive(str(tmp_path / "new"))
    new_root = tmp_path / "new" / "ตรวจบิล"
    assert out["root"] == str(new_root) and out["copied"] == 1
    assert listing(new_root) == listing(root)                             # โฟลเดอร์เดิมยังอยู่ครบ


def test_safe_name():
    assert archive.safe_name('a:b?.xlsx') == "a_b_.xlsx"
    assert archive.safe_name("C:\\Users\\x\\บิล.xlsx") == "บิล.xlsx"
    assert archive.safe_name("dir/sub/บิล.xlsx ") == "บิล.xlsx"


def test_migrate_v1_database(tmp_path):
    db = tmp_path / "data.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE files (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
                            imported_at TEXT NOT NULL, parsed_json TEXT NOT NULL, blob BLOB);
        CREATE TABLE payments (bi_number TEXT PRIMARY KEY, paid_date TEXT NOT NULL, note TEXT DEFAULT '', recorded_at TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        INSERT INTO payments VALUES ('NNCBI-260901', '2026-03-15', '', '2026-03-15T10:00:00');
    """)
    con.commit()
    con.close()
    st = Store(db)
    assert [r for r in st.file_rows()] == []
    assert "NNCBI-260901" in st.payments()
    assert list((tmp_path / "backups").glob("*before-schema-2.db"))


def test_empty_year_folder_removed_after_move(tmp_path):
    api, root = make_api(tmp_path)
    (root / "2568" / "03 มีนาคม 2568").mkdir(parents=True)
    api.sync_archive()
    assert not (root / "2568").exists()
