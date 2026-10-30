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
