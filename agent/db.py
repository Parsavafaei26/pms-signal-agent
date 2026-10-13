"""Database set-up and loading."""
import csv
import re
import sqlite3
from . import config


def connect(path=None):
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init(con):
    con.executescript((config.SQL_DIR / "schema.sql").read_text())
    con.executescript((config.SQL_DIR / "seed.sql").read_text())
    con.commit()


def is_midline(row):
    text = " ".join([row["event_description"], row["brand_name"], row["generic_name"]])
    return bool(re.search("midline", text, re.I))


def load_reports(con, csv_path=None, sample_ids_path=None):
    """Load MAUDE reports. Midline catheters are out of scope; sample ids form the coding queue."""
    csv_path = csv_path or config.DATA_DIR / "maude_reports.csv"
    sample = set()
    if sample_ids_path is None:
        sample_ids_path = config.DATA_DIR / "sample_ids.txt"
    if sample_ids_path and sample_ids_path.exists():
        sample = set(sample_ids_path.read_text().split())
    n = 0
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            con.execute(
                """INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["report_number"], r["date_received"], r["quarter_received"], r["event_type"],
                 r["brand_name"], r["manufacturer"], r["product_code"], r["device_problems"],
                 r["patient_problems"], r["event_description"], r["manufacturer_narrative"],
                 0 if is_midline(r) else 1, 1 if r["report_number"] in sample else 0))
            n += 1
    con.commit()
    return n


def uncoded_queue(con):
    return con.execute(
        """SELECT r.* FROM reports r LEFT JOIN labels l USING (report_number)
           WHERE r.in_sample = 1 AND r.in_scope = 1 AND l.report_number IS NULL
           ORDER BY r.quarter, r.report_number""").fetchall()
