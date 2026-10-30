from datetime import date
from decimal import Decimal as D

from app.checker import billing_valid, check_file, sales_countable
from app.reader import parse_filename, read_file
from tests.conftest import fixture_file


def codes(issues):
    return sorted(i.code for i in issues)


def test_filename_parts():
    assert parse_filename("ใบกำกับ NNCIV-269053-B045-R047_ลูกค้า_PO123 6-2-69.xlsx") == ("NNCIV-269053", "045", "047")
    assert parse_filename("NNCIV-260030-R024_x.xlsx") == ("NNCIV-260030", "", "024")
    assert parse_filename("random.xlsx") == ("", "", "")


def test_full_set_reads_all_docs():
    pf = read_file(fixture_file("269001", "B901"))
    assert pf.ok
    iv = pf.iv
    assert iv.number == "NNCIV-269001" and iv.date == date(2026, 2, 3)
    assert iv.tax_id == "0000000000001"
    assert (iv.subtotal, iv.vat, iv.total) == (D("30900.00"), D("2163.00"), D("33063.00"))
    assert [i.desc for i in iv.items] == ["Notebook Model X1", "Mouse M1"]
    assert iv.items[0].extra == ["SN : AAA111 / BBB222"]
    assert pf.bi.number == "NNCBI-260901" and pf.bi.ref_iv == "NNCIV-269001"
    assert pf.bi.wht is None and pf.bi.total == D("33063.00")
    assert pf.re.number == "NNCRECEIPT-260901"
    issues = check_file(pf)
    assert issues == []
    assert billing_valid(pf, issues)


def test_vat_included():
    pf = read_file(fixture_file("269002"))
    assert pf.iv.vat_included
    assert (pf.iv.subtotal, pf.iv.vat, pf.iv.total) == (D("595.33"), D("41.67"), D("637.00"))
    assert codes(check_file(pf)) == ["VAT_INCLUDED"]


def test_stale_receipt_item_name_and_phone():
    pf = read_file(fixture_file("269003"))
    issues = check_file(pf)
    assert codes(issues) == ["EXTRA_ITEM", "NAME", "PHONE"]
    extra = next(i for i in issues if i.code == "EXTRA_ITEM")
    assert extra.doc == "RE" and "Old Item Z9" in extra.message
    # ปัญหาอยู่ที่ใบเสร็จ และชื่อลูกค้าเป็นแค่ข้อสังเกต → ใบวางบิลยังนับ
    assert billing_valid(pf, issues)


def test_copied_billing_sheet_without_B():
    pf = read_file(fixture_file("269004"))
    issues = check_file(pf)
    assert codes(issues) == ["BI_LINK", "TERM_CONFLICT"]
    assert not billing_valid(pf, issues)


def test_items_not_summing_blocks_sales():
    pf = read_file(fixture_file("269006"))
    issues = check_file(pf)
    assert codes(issues) == ["SUM_ITEMS"]
    assert not sales_countable(issues)


def test_not_excel(tmp_path):
    p = tmp_path / "x.xlsx"
    p.write_text("hello")
    pf = read_file(p)
    assert not pf.ok and pf.errors


# ---- กรณีที่เจอจากไฟล์จริงเดือน ม.ค. 69 ----
from datetime import date as _date

from openpyxl import Workbook

from app.checker import _match_lines
from app.reader import Doc, Item, date_from_filename
from tests import make_fixtures as mk


def _iv(*descs):
    return Doc(kind="IV", sheet="x", items=[Item(desc=d, extra=list(e)) for d, *e in descs])


def test_short_names_and_qty_lines_are_not_extra():
    iv = _iv(('Dell Pro 24 Monitor 23.8" 1920x 1080 (E2425HSM)',),
             ("Lofree FLOW 2 Low Profile Wireless Mechanical Keyboard,",),
             ("Whole Genome Bacteria Analysis (Short Reads)", "Samples"))
    lines = ['Dell Pro 24 Monitor 23.8" (E2425HSM) จำนวน 1 ชุด', "Lofree FLOW2 Low Profile Wireless Mechanical KB 1ชุด",
             "Whole Genome Bacteria Analysis (Short Reads)", "3 Samples"]
    assert _match_lines(iv, lines) == ([], [])


def test_stale_item_with_different_model_code_is_extra():
    iv = _iv(("HP 416A Black Original LaserJet Toner Cartridge",), ("HP Color LaserJet Enterprise M455dn Printer",))
    extra, _ = _match_lines(iv, ["HP 416A Black Original LaserJet Toner Cartridgeจำนวน 5 ชุด", "HP 119A Toner BK จำนวน 2 ชุด"])
    assert extra == ["HP 119A Toner BK จำนวน 2 ชุด"]


def test_date_from_filename():
    assert date_from_filename("กำกับ NNCIV-269023-B017-R017 ลูกค้า ซ่อม NB @ 2 Set ส่งของ 19-1-69.xlsx") == _date(2026, 1, 19)
    assert date_from_filename("NNCIV-260001.xlsx") is None


def test_blank_invoice_date_uses_filename_and_alerts(tmp_path):
    wb = Workbook()
    mk.iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ (2)", "NNCIV-269100", None, mk.CUST_A, [("Repair", 1, 2500)])
    del wb["Sheet"]
    p = tmp_path / "กำกับ NNCIV-269100 ส่งของ 19-1-69.xlsx"
    wb.save(p)
    pf = read_file(p)
    assert pf.ok and pf.iv.date == _date(2026, 1, 19) and pf.iv.date_source == "filename"
    issues = check_file(pf)
    assert [i.code for i in issues] == ["DATE_MISSING"] and issues[0].level == "red"
    assert sales_countable(issues)


def test_label_says_excluding_vat_but_numbers_decide(tmp_path):
    """ฟอร์มที่ใช้ป้าย 'ราคาไม่รวมภาษีมูลค่าเพิ่ม' ตรงยอดก่อน VAT และรายการรวม = ก่อน VAT"""
    wb = Workbook()
    mk.iv_sheet(wb, "ใบกำกับภาษี ต้นฉบับ", "NNCIV-269101", "5/1/2569", mk.CUST_A, [("WGS Assembly", 26, 500)])
    ws = wb["ใบกำกับภาษี ต้นฉบับ"]
    ws["D38"], ws["D42"] = "ราคาไม่รวมภาษีมูลค่าเพิ่ม ", "ราคารวมทั้งสิ้น Net Total "
    del wb["Sheet"]
    p = tmp_path / "b.xlsx"
    wb.save(p)
    pf = read_file(p)
    assert not pf.iv.vat_included
    assert (pf.iv.subtotal, pf.iv.vat, pf.iv.total) == (D("13000.00"), D("910.00"), D("13910.00"))
    assert check_file(pf) == []
