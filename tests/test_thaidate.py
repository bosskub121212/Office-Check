from datetime import date, datetime

from app import thaidate as t


def test_parse_be_slash():
    assert t.parse_thai_date("6/2/2569") == date(2026, 2, 6)


def test_parse_short_year_dash():
    assert t.parse_thai_date("30-1-69") == date(2026, 1, 30)


def test_parse_datetime_be_year():
    assert t.parse_thai_date(datetime(2569, 2, 9)) == date(2026, 2, 9)


def test_parse_garbage():
    assert t.parse_thai_date("เครดิต 30 วัน") is None


def test_term_days():
    assert t.parse_term_days("เครดิต 30 วัน") == 30
    assert t.parse_term_days("เงินสด") == 0
    assert t.parse_term_days("") is None


def test_due_credit_30_crosses_month():
    due, conflict = t.due_date(date(2026, 2, 6), "เครดิต 30 วัน", "เครดิต 30 วัน")
    assert due == date(2026, 3, 8) and not conflict


def test_due_conflict_uses_payment_term():
    due, conflict = t.due_date(date(2026, 1, 30), "เงินสด", "เครดิต 30 วัน")
    assert due == date(2026, 1, 30) and conflict


def test_due_explicit_date():
    due, _ = t.due_date(date(2026, 2, 1), "", "15/3/2569")
    assert due == date(2026, 3, 15)


def test_format():
    assert t.fmt(date(2026, 3, 11)) == "11 มี.ค. 69"
    assert t.month_label("2026-02") == "กุมภาพันธ์ 2569"
