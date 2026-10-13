"""Tests: python3 -m unittest -v"""
import io
import json
import sqlite3
import unittest
from pathlib import Path

from agent import config, db, signals, validator
from agent.agent import PMSAgent
from agent.coders import ClaudeCoder, ReplayCoder

GOOD = {"primary_fm": "FM01", "secondary_fm": "none", "phase": "P3", "severity": "S2", "contributor": "UNK",
        "retained_fragment": "N", "user_harm": "N", "confidence": "high", "quote": "hole at 5 cm", "note": "x"}


def memory_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    return con


def add_report(con, rid, quarter, text="TEXT"):
    con.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, quarter.replace("-Q", "0") + "01", quarter, "Malfunction", "PICC", "M", "LJS",
                 "", "", text, "", 1, 1))


class TestValidator(unittest.TestCase):
    def test_good_label_passes(self):
        self.assertEqual(validator.validate(GOOD), [])

    def test_bad_values_rejected(self):
        bad = GOOD | {"primary_fm": "FM99", "severity": "S9"}
        errs = validator.validate(bad)
        self.assertTrue(any("primary_fm" in e for e in errs) and any("severity" in e for e in errs))

    def test_secondary_must_differ(self):
        self.assertTrue(validator.validate(GOOD | {"secondary_fm": "FM01"}))

    def test_quote_required(self):
        self.assertTrue(validator.validate(GOOD | {"quote": " "}))

    def test_fm08_phase(self):
        self.assertTrue(validator.validate(GOOD | {"primary_fm": "FM08", "phase": "P3"}))

    def test_review_routing(self):
        self.assertEqual(validator.review_reasons(GOOD), [])
        self.assertIn("severity S3", validator.review_reasons(GOOD | {"severity": "S3"}))
        self.assertIn("retained fragment", validator.review_reasons(GOOD | {"retained_fragment": "Y"}))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeAPI:
    """Stands in for the Anthropic API: first answer breaks a rule, second is valid."""
    def __init__(self, answers):
        self.answers, self.requests = list(answers), []

    def __call__(self, req, timeout=None):
        self.requests.append(json.loads(req.data))
        label = self.answers.pop(0)
        body = {"content": [{"type": "tool_use", "id": f"tu_{len(self.requests)}", "name": "record_label",
                             "input": label}]}
        return FakeResponse(json.dumps(body).encode())


class TestClaudeCoderRetry(unittest.TestCase):
    def test_retry_with_validator_feedback(self):
        con = memory_db()
        add_report(con, "R1", "2024-Q1")
        api = FakeAPI([GOOD | {"secondary_fm": "FM01"}, GOOD])
        coder = ClaudeCoder(api_key="test", model="test-model", opener=api)
        agent = PMSAgent(con, coder)
        agent.run(db.uncoded_queue(con))
        self.assertEqual(agent.stats["coded"], 1)
        self.assertEqual(agent.stats["retried"], 1)
        first, second = api.requests
        self.assertEqual(first["tool_choice"], {"type": "tool", "name": "record_label"})
        tool_result = second["messages"][-1]["content"][0]
        self.assertEqual(tool_result["type"], "tool_result")
        self.assertTrue(tool_result["is_error"])
        self.assertIn("secondary_fm must differ", tool_result["content"])

    def test_rejected_after_retries_goes_to_review(self):
        con = memory_db()
        add_report(con, "R1", "2024-Q1")
        bad = GOOD | {"quote": ""}
        coder = ClaudeCoder(api_key="t", model="m", opener=FakeAPI([bad, bad, bad]))
        agent = PMSAgent(con, coder)
        agent.run(db.uncoded_queue(con))
        self.assertEqual(agent.stats["rejected"], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM labels").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT reason FROM review_queue").fetchone()[0],
                         "label failed validation after retries")


class TestSQL(unittest.TestCase):
    def test_complaints_view_dedups_groups_and_voided(self):
        con = memory_db()
        for rid in ["A", "B", "C"]:
            add_report(con, rid, "2024-Q1")
        rows = [("A", "A", 0), ("B", "A", 0), ("C", "C", 1)]   # B repeats A's complaint; C voided
        for rid, grp, void in rows:
            con.execute("INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, "FM01", None, "P3", "S2", "UNK", 0, 0, grp, "high", "q", "", void,
                         "t", "1.2", "now", "not_required"))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0], 1)

    def test_rising_failure_mode_detected(self):
        con = memory_db()
        quarters = [f"{y}-Q{q}" for y in (2023, 2024) for q in (1, 2, 3, 4)]
        n = 0
        for i, quarter in enumerate(quarters):
            k = 1 if i < 4 else 2                              # 4 in first window, 8 in second
            for _ in range(k):
                n += 1
                add_report(con, f"R{n}", quarter)
                con.execute("INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (f"R{n}", "FM04", None, "P3", "S2", "UNK", 0, 0, f"R{n}", "high", "q", "",
                             0, "t", "1.2", "now", "not_required"))
        found = [s for s in signals.run_checks(con) if s["check_name"] == "rising_failure_mode"]
        self.assertEqual([(s["subject"], s["current_n"], s["baseline_n"]) for s in found], [("FM04", 8, 4)])


class TestReplayEndToEnd(unittest.TestCase):
    def test_project1_sample(self):
        con = memory_db()
        db.load_reports(con)
        agent = PMSAgent(con, ReplayCoder())
        agent.run(db.uncoded_queue(con))
        self.assertEqual(agent.stats["coded"], 300)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0], 288)


if __name__ == "__main__":
    unittest.main()
