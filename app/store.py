"""ฐานข้อมูล SQLite: ไฟล์ที่นำเข้า (เก็บผลอ่าน + สำเนาไฟล์) และประวัติการรับเงิน"""
from __future__ import annotations

import json
import sqlite3
import zlib
from datetime import date, datetime
from pathlib import Path

from .reader import ParsedFile

SCHEMA_VERSION = 1
KEEP_BACKUPS = 10

_MIGRATIONS = {
    1: """
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        imported_at TEXT NOT NULL,
        parsed_json TEXT NOT NULL,
        blob BLOB
    );
    CREATE TABLE IF NOT EXISTS payments (
        bi_number TEXT PRIMARY KEY,
        paid_date TEXT NOT NULL,
        note TEXT DEFAULT '',
        recorded_at TEXT NOT NULL
    );
    """,
}


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._migrate(existed)

    # ------------------------------------------------------------ schema
    def _version(self) -> int:
        try:
            row = self.db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
            return int(row["v"]) if row else 0
        except sqlite3.OperationalError:
            return 0

    def _migrate(self, existed: bool):
        cur = self._version()
        if cur >= SCHEMA_VERSION:
            return
        if existed and cur > 0:
            self.backup(f"before-schema-{SCHEMA_VERSION}")
        for v in range(cur + 1, SCHEMA_VERSION + 1):
            self.db.executescript(_MIGRATIONS[v])
            self.db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema_version', ?)", (str(v),))
        self.db.commit()

    # ------------------------------------------------------------ backup
    def backup(self, reason: str = "manual") -> Path:
        bdir = self.path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"data-{datetime.now():%Y%m%d-%H%M%S}-{reason}.db"
        with sqlite3.connect(dest) as out:
            self.db.backup(out)
        olds = sorted(bdir.glob("data-*.db"))
        for old in olds[:-KEEP_BACKUPS]:
            old.unlink(missing_ok=True)
        return dest

    # ------------------------------------------------------------ files
    def has_sha(self, sha: str) -> bool:
        return self.db.execute("SELECT 1 FROM files WHERE sha256=?", (sha,)).fetchone() is not None

    def add_file(self, pf: ParsedFile, raw: bytes | None) -> int | None:
        """คืน id ของไฟล์ หรือ None ถ้าไฟล์นี้ (เนื้อหาเดียวกันทุกไบต์) เคยนำเข้าแล้ว"""
        if self.has_sha(pf.sha256):
            return None
        cur = self.db.execute(
            "INSERT INTO files(filename, sha256, imported_at, parsed_json, blob) VALUES(?,?,?,?,?)",
            (pf.filename, pf.sha256, datetime.now().isoformat(timespec="seconds"),
             json.dumps(pf.to_dict(), ensure_ascii=False), zlib.compress(raw) if raw else None))
        self.db.commit()
        return cur.lastrowid

    def delete_file(self, file_id: int):
        self.db.execute("DELETE FROM files WHERE id=?", (file_id,))
        self.db.commit()

    def files(self) -> list[tuple[int, str, ParsedFile]]:
        rows = self.db.execute("SELECT id, imported_at, parsed_json FROM files ORDER BY id").fetchall()
        return [(r["id"], r["imported_at"], ParsedFile.from_dict(json.loads(r["parsed_json"]))) for r in rows]

    def file_blob(self, file_id: int) -> tuple[str, bytes] | None:
        r = self.db.execute("SELECT filename, blob FROM files WHERE id=?", (file_id,)).fetchone()
        if not r or r["blob"] is None:
            return None
        return r["filename"], zlib.decompress(r["blob"])

    # ------------------------------------------------------------ payments
    def set_paid(self, bi_number: str, paid: date | None, note: str = ""):
        if paid is None:
            self.db.execute("DELETE FROM payments WHERE bi_number=?", (bi_number,))
        else:
            self.db.execute(
                "INSERT OR REPLACE INTO payments(bi_number, paid_date, note, recorded_at) VALUES(?,?,?,?)",
                (bi_number, paid.isoformat(), note, datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def payments(self) -> dict[str, date]:
        rows = self.db.execute("SELECT bi_number, paid_date FROM payments").fetchall()
        return {r["bi_number"]: date.fromisoformat(r["paid_date"]) for r in rows}

    def close(self):
        self.db.close()
