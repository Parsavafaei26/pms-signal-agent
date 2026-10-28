"""Tests for the live-run machinery, using a simulated API (no key, no cost).

    python3 -m unittest -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

from agent import config, evaluate
from agent.coders import BudgetExceeded, ClaudeCoder, price_of

sys.path.insert(0, str(config.ROOT / "scripts"))
import live_eval                                                     # noqa: E402

GOOD = {"primary_fm": "FM01", "secondary_fm": "none", "phase": "P3", "severity": "S2", "contributor": "UNK",
        "retained_fragment": "N", "user_harm": "N", "confidence": "high", "quote": "hole", "note": "x"}
USAGE = {"input_tokens": 600, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 3500,
         "output_tokens": 200}
REPORT = {"report_number": "R1", "event_type": "Malfunction", "brand_name": "PICC",
          "fda_device_problems": "", "fda_patient_problems": "", "event_description": "hole",
          "manufacturer_narrative": ""}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SimulatedAPI:
    """Answers every call with a label from `answer(report_text)` and a fixed usage block."""
    def __init__(self, answer=lambda text: GOOD, fail_first=0):
        self.answer, self.fail_first, self.requests = answer, fail_first, []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        self.requests.append(body)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {"retry-after": "1"}, io.BytesIO(b"{}"))
        first = body["messages"][0]["content"]
        out = {"content": [{"type": "tool_use", "id": f"tu{len(self.requests)}", "name": "record_label",
                            "input": self.answer(first)}], "usage": USAGE}
        return Resp(json.dumps(out).encode())


def coder(api, **kw):
    return ClaudeCoder(api_key="test", model="claude-haiku-5-5", opener=api, sleep=lambda s: None, **kw)


class TestCostTracking(unittest.TestCase):
    def test_price_of_uses_all_token_types(self):
        inp, write, read, out = config.PRICES["claude-sonnet-5-5"]
        expected = (600 * inp + 3500 * read + 200 * out) / 1e6
        self.assertAlmostEqual(price_of("claude-sonnet-5-5", USAGE), expected)
        self.assertIsNone(price_of("unknown-model", USAGE))

    def test_usage_is_recorded_per_call(self):
        c = coder(SimulatedAPI())
        c.code(REPORT)
        s = c.usage_summary()
        self.assertEqual((s["api_calls"], s["cache_read_tokens"], s["output_tokens"]), (1, 3500, 200))
        self.assertGreater(s["cost_usd"], 0)

    def test_system_prompt_is_cached(self):
        api = SimulatedAPI()
        coder(api).code(REPORT)
        self.assertEqual(api.requests[0]["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn(config.RULES_FILE.read_text()[:300], api.requests[0]["system"][0]["text"])

    def test_budget_cap_stops_before_the_next_call(self):
        api = SimulatedAPI()
        c = coder(api, max_cost=1e-9)
        c.code(REPORT)                      # first call is allowed, and spends more than the cap
        with self.assertRaises(BudgetExceeded):
            c.code(REPORT | {"report_number": "R2"})
        self.assertEqual(len(api.requests), 1)

    def test_rate_limit_is_retried(self):
        api = SimulatedAPI(fail_first=2)
        label = coder(api).code(REPORT)
        self.assertEqual(label["primary_fm"], "FM01")
        self.assertEqual(len(api.requests), 3)

    def test_unpriced_model_is_refused(self):
        with self.assertRaises(RuntimeError):
            ClaudeCoder(api_key="t", model="some-new-model", opener=SimulatedAPI())


class TestEnv(unittest.TestCase):
    def test_env_file_loaded_without_overriding(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# comment\nPMS_TEST_A=from_file\nPMS_TEST_B='quoted'\n")
            os.environ["PMS_TEST_A"] = "already_set"
            config.load_env(p)
            self.assertEqual(os.environ["PMS_TEST_A"], "already_set")
            self.assertEqual(os.environ["PMS_TEST_B"], "quoted")
            del os.environ["PMS_TEST_A"], os.environ["PMS_TEST_B"]


class TestAgreement(unittest.TestCase):
    def test_baselines_reproduce_project1_figures(self):
        manual = evaluate.load_labels(live_eval.MANUAL)
        v11 = evaluate.compare(manual, evaluate.load_labels(live_eval.BASELINES["Earlier AI run, rules v1.1"]))
        v12 = evaluate.compare(manual, evaluate.load_labels(live_eval.BASELINES["Earlier AI run, rules v1.2"]))
        self.assertEqual(v11["n"], 100)
        self.assertAlmostEqual(v11["primary_fm"]["agreement"], 0.93)
        self.assertAlmostEqual(round(v11["primary_fm"]["kappa"], 2), 0.90)
        self.assertAlmostEqual(v11["severity"]["agreement"], 0.61)
        self.assertAlmostEqual(v12["severity"]["agreement"], 0.85)
        self.assertAlmostEqual(round(v12["severity"]["kappa"], 2), 0.78)

    def test_kappa_edge_cases(self):
        self.assertEqual(evaluate.kappa(list("aab"), list("aab")), 1.0)
        self.assertAlmostEqual(evaluate.kappa(list("ab"), list("ba")), -1.0)


class TestLiveEvalEndToEnd(unittest.TestCase):
    def test_simulated_run_writes_scored_report(self):
        """Simulated model that copies the manual label for half the reports and says FM02 otherwise."""
        manual = evaluate.load_labels(live_eval.MANUAL)

        def answer(text):
            rid = text.split("\n")[0].split(": ")[1]
            m = manual[rid]
            lab = GOOD | {k: m[k] for k in evaluate.FIELDS}
            if lab["primary_fm"] == "FM08" and lab["phase"] not in ("P1", "P2"):
                lab["phase"] = "P1"
            if sorted(manual).index(rid) % 2:
                lab["primary_fm"] = "FM02" if m["primary_fm"] != "FM02" else "FM03"
                if lab["secondary_fm"] == lab["primary_fm"]:
                    lab["secondary_fm"] = "none"
            return lab

        reports = live_eval.review_reports()
        factory = lambda model, max_cost: ClaudeCoder(api_key="t", model=model, max_cost=max_cost,
                                                      opener=SimulatedAPI(answer), sleep=lambda s: None)
        labels, attempts, c, stats = live_eval.run_model("claude-haiku-5-5", reports, 5.0, factory)
        self.assertEqual(stats["coded"], 100)
        with tempfile.TemporaryDirectory() as d:
            live_eval.write_outputs("claude-haiku-5-5", reports, labels, attempts, c, Path(d))
            self.assertTrue((Path(d) / "labels_claude-haiku-5-5.csv").exists())
            scored = evaluate.load_labels(Path(d) / "labels_claude-haiku-5-5.csv")
        comp = evaluate.compare(manual, scored)
        self.assertAlmostEqual(comp["primary_fm"]["agreement"], 0.5)
        md = live_eval.report_md([("Live: sim", scored, stats, c.usage_summary())], manual, 100)
        self.assertIn("| Primary failure mode | 50%", md)


if __name__ == "__main__":
    unittest.main()
