"""Writes the human-facing outputs: review queue CSV and a draft signal report (template, not AI-written)."""
import csv
from collections import defaultdict
from . import config

CHECK_TITLES = {
    "rising_failure_mode": "Rising failure modes (rolling 4 quarters vs the previous 4)",
    "keyword_cluster": "Component keyword clusters",
    "serious_event": "Serious events for individual review",
    "share_shift": "EXPLORATORY: share of complaints up 15+ points (added after first run)",
}


def write_review_queue(con, path=None):
    path = path or config.OUT_DIR / "review_queue.csv"
    rows = con.execute(
        """SELECT q.report_number, r.quarter, l.primary_fm, l.severity, q.reason, l.quote
           FROM review_queue q JOIN reports r USING (report_number)
           LEFT JOIN labels l USING (report_number)
           WHERE q.resolved = 0 ORDER BY r.quarter, q.report_number""").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["report_number", "quarter", "primary_fm", "severity", "reason", "quote"])
        w.writerows([tuple(r) for r in rows])
    return len(rows)


def write_signal_report(con, agent, found, path=None):
    path = path or config.OUT_DIR / "signal_report.md"
    names = dict(con.execute("SELECT code, name FROM failure_modes").fetchall())
    n_complaints = con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    by_check = defaultdict(list)
    for s in found:
        by_check[s["check_name"]].append(s)
    lines = [
        "# Draft PMS signal report",
        "",
        f"*Run {agent.run_id} · coder `{agent.coder.name}` · rules v{agent.coder.rules_version} · "
        f"DRAFT for review, not a regulatory decision.*",
        "",
        f"Unique complaints in database: {n_complaints}. Reports coded this run: {agent.stats['coded']}; "
        f"validation retries: {agent.stats['retried']}; rejected: {agent.stats['rejected']}; "
        f"errors: {agent.stats['errors']}; routed to human review: {agent.stats['routed']}.",
        "",
        f"Thresholds (set before the run): {config.SIGNAL_PARAMS}.",
        "",
    ]
    for check in ["rising_failure_mode", "share_shift", "keyword_cluster", "serious_event"]:
        items = by_check.get(check, [])
        lines += [f"## {CHECK_TITLES[check]}: {len(items)}", ""]
        if not items:
            lines += ["None.", ""]
            continue
        if check == "serious_event":
            lines += ["| Quarter | Report | Detail |", "| --- | --- | --- |"]
            lines += [f"| {s['period']} | {s['subject']} | {s['detail']} |" for s in items]
        else:
            lines += ["| Period | Subject | Current | Baseline | Detail |", "| --- | --- | --- | --- | --- |"]
            for s in items:
                subj = f"{s['subject']} {names.get(s['subject'], '')}".strip()
                lines.append(f"| {s['period']} | {subj} | {s['current_n']} | {s['baseline_n'] if s['baseline_n'] is not None else ''} | {s['detail']} |")
        lines.append("")
    lines += ["## Reviewer sign-off", "", "- [ ] Signals assessed and actions recorded",
              "- [ ] Review queue cleared", "", "Reviewer: ________  Date: ________", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
