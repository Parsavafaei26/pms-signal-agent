"""The agent loop.

For each uncoded report in the queue:  code -> validate -> (retry with feedback) -> store -> route.
Then: run SQL signal checks -> store signals -> write the review queue and a draft signal report.
Every step is written to audit_log so a reviewer can reconstruct what happened.
"""
import datetime as dt
import uuid
from . import config, signals, validator
from .coders import BudgetExceeded


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class PMSAgent:
    def __init__(self, con, coder, max_retries=config.MAX_RETRIES):
        self.con, self.coder, self.max_retries = con, coder, max_retries
        self.run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.stats = {"coded": 0, "retried": 0, "rejected": 0, "errors": 0, "routed": 0}

    def log(self, step, outcome, report_number=None, detail=None):
        self.con.execute("INSERT INTO audit_log (run_id, ts, step, report_number, outcome, detail) "
                         "VALUES (?,?,?,?,?,?)", (self.run_id, now(), step, report_number, outcome, detail))

    # ---- coding ----
    def code_one(self, report):
        rid = report["report_number"]
        feedback = None
        for attempt in range(self.max_retries + 1):
            try:
                label = self.coder.code(report, feedback)
            except BudgetExceeded:
                raise                                      # stop the whole run, not just this report
            except Exception as exc:                       # network, missing label, bad response
                self.log("code", "error", rid, str(exc)[:300])
                self.stats["errors"] += 1
                return None
            errors = validator.validate(label)
            if not errors:
                self.log("validate", "ok", rid, f"attempt {attempt + 1}")
                return label
            self.log("validate", "retry" if attempt < self.max_retries else "rejected", rid, "; ".join(errors))
            if attempt < self.max_retries:
                self.stats["retried"] += 1
            feedback = errors
        self.stats["rejected"] += 1
        self.queue_review(rid, "label failed validation after retries")
        return None

    def store(self, report, label):
        reasons = validator.review_reasons(label)
        sec = label.get("secondary_fm") or "none"
        self.con.execute(
            """INSERT OR REPLACE INTO labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (report["report_number"], label["primary_fm"], None if sec == "none" else sec,
             label["phase"], label["severity"], label["contributor"],
             1 if label["retained_fragment"] == "Y" else 0, 1 if label["user_harm"] == "Y" else 0,
             label.get("complaint_group") or report["report_number"], label["confidence"],
             label.get("quote"), label.get("note"), 1 if label.get("voided") else 0,
             self.coder.name, self.coder.rules_version, now(),
             "pending" if reasons else "not_required"))
        self.log("code", "ok", report["report_number"], f"{label['primary_fm']} {label['severity']}")
        self.stats["coded"] += 1
        if reasons:
            self.queue_review(report["report_number"], ", ".join(reasons))

    def queue_review(self, rid, reason):
        self.con.execute("INSERT INTO review_queue (report_number, reason, created_at) VALUES (?,?,?)",
                         (rid, reason, now()))
        self.log("route", "flagged", rid, reason)
        self.stats["routed"] += 1

    # ---- signals ----
    def detect_signals(self):
        found = signals.run_checks(self.con)
        for s in found:
            self.con.execute(
                """INSERT INTO signals (run_id, check_name, period, subject, current_n, baseline_n, detail, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (self.run_id, s["check_name"], s["period"], s["subject"], s["current_n"], s["baseline_n"],
                 s["detail"], now()))
        self.log("signal", "ok", None, f"{len(found)} signals; params {config.SIGNAL_PARAMS}")
        return found

    def run(self, queue, limit=None):
        self.log("run", "ok", None, f"coder={self.coder.name} rules={self.coder.rules_version}")
        for i, report in enumerate(queue):
            if limit is not None and i >= limit:
                break
            try:
                label = self.code_one(report)
            except BudgetExceeded as exc:
                self.stats["stopped"] = str(exc)
                self.log("run", "stopped", report["report_number"], str(exc))
                break
            if label is not None:
                self.store(report, label)
            self.con.commit()
        found = self.detect_signals()
        self.con.commit()
        return found
