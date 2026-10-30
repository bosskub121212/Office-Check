from datetime import date
from decimal import Decimal as D

from app.ledger import Ledger
from app.reader import read_file
from app.store import Store
from tests.conftest import FIX, fixture_file


def load_all(tmp_path, order=None):
    st = Store(tmp_path / "data.db")
    files = sorted(FIX.glob("*.xlsx"))
    if order == "reverse":
        files = files[::-1]
    for f in files:
        st.add_file(read_file(f), f.read_bytes())
    return st


def test_reimport_same_bytes_is_skipped(tmp_path):
    st = Store(tmp_path / "data.db")
    f = fixture_file("269001", "B901")
    assert st.add_file(read_file(f), f.read_bytes()) is not None
    assert st.add_file(read_file(f), f.read_bytes()) is None


def test_duplicate_iv_oldest_date_wins_regardless_of_order(tmp_path):
    for order in (None, "reverse"):
        st = load_all(tmp_path / (order or "fwd"), order)
        lg = Ledger(st.files(), st.payments())
        kept = [b for b in lg.bills if b.iv.number == "NNCIV-269001"]
        assert len(kept) == 1 and kept[0].iv.date == date(2026, 2, 3)
        dropped = [b for b in lg.dropped if b.iv.number == "NNCIV-269001"]
        assert len(dropped) == 1 and dropped[0].issues[0].code == "DUP_IV"


def test_duplicate_bi_number_later_bill_not_billed(tmp_path):
    st = load_all(tmp_path)
    lg = Ledger(st.files(), st.payments())
    b5 = next(b for b in lg.bills if b.iv.number == "NNCIV-269005")
    assert not b5.billed and b5.countable
    assert b5.issues[0].code == "DUP_BI"
    b1 = next(b for b in lg.bills if b.iv.number == "NNCIV-269001")
    assert b1.billed


def test_february_totals(tmp_path):
    st = load_all(tmp_path)
    lg = Ledger(st.files(), st.payments())
    t = lg.totals(lg.in_month("2026-02"))
    # นับ: 269001 (30,900) + 269002 (595.33) + 269003 (14,000) + 269004 (5,000) + 269005 (3,000)
    # ไม่นับ: 269006 (ผลรวมรายการไม่ตรง) และไฟล์ copy ของ 269001
    assert t["sub"] == D("53495.33")
    assert t["vat"] == D("3744.67")
    assert t["total"] == D("57240.00")
    # วางบิล: 269001 + 269003 (269004 ไม่มี B, 269005 เลขซ้ำ)
    assert t["billed_count"] == 2
    assert t["billed_total"] == D("33063.00") + D("14980.00")


def test_due_month_and_payment_learning(tmp_path):
    st = load_all(tmp_path)
    lg = Ledger(st.files(), st.payments())
    march_due = [b.iv.number for b in lg.due_in_month("2026-03")]
    assert march_due == ["NNCIV-269001", "NNCIV-269003"]           # 3 ก.พ.+30 = 5 มี.ค., 10 ก.พ.+30 = 12 มี.ค.
    assert [b.iv.number for b in lg.due_in_month("2026-04")] == ["NNCIV-269007"]
    assert len(lg.payables()) == 3

    # ลูกค้าเอจ่ายบิล 269001 ช้ากว่ากำหนด 10 วัน → บิล 269007 ของลูกค้าเอ คาดว่าได้รับช้าไป 10 วัน
    st.set_paid("NNCBI-260901", date(2026, 3, 15))
    lg = Ledger(st.files(), st.payments())
    assert [b.iv.number for b in lg.payables()] == ["NNCIV-269003", "NNCIV-269007"]
    b7 = next(b for b in lg.bills if b.iv.number == "NNCIV-269007")
    assert b7.due == date(2026, 4, 1) and b7.expected == date(2026, 4, 11)
    st.set_paid("NNCBI-260901", None)
    assert st.payments() == {}


def test_backup_rotation(tmp_path):
    st = Store(tmp_path / "data.db")
    for i in range(12):
        st.backup(f"t{i:02d}")
    assert len(list((tmp_path / "backups").glob("*.db"))) == 10
    # ต้องไม่มีไฟล์ backup ถูกเปิดค้าง (บน Windows ไฟล์ที่เปิดค้างจะลบไม่ได้)
    import os
    fd_dir = "/proc/self/fd"
    if os.path.isdir(fd_dir):
        held = []
        for f in os.listdir(fd_dir):
            try:
                held.append(os.readlink(os.path.join(fd_dir, f)))
            except OSError:
                pass
        assert not [h for h in held if "backups" in h]
