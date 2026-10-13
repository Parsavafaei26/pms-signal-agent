"""Runs the named SQL checks in sql/signals.sql."""
import re
from . import config


def load_checks(path=None):
    text = (path or config.SQL_DIR / "signals.sql").read_text()
    checks = {}
    for block in re.split(r"^-- name: ", text, flags=re.M)[1:]:
        name, sql = block.split("\n", 1)
        checks[name.strip()] = sql.strip().rstrip(";")
    return checks


def run_checks(con, params=None):
    params = params or config.SIGNAL_PARAMS
    results = []
    for name, sql in load_checks().items():
        needed = {k: v for k, v in params.items() if f":{k}" in sql}
        for row in con.execute(sql, needed).fetchall():
            results.append({"check_name": name, **dict(row)})
    return results
