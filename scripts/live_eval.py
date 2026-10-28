"""Live evaluation: run real models on the 100 reports that were reviewed blind by hand.

    python3 scripts/live_eval.py --dry-run                         # cost estimate, no key needed
    python3 scripts/live_eval.py --list-models                     # model ids your key can use
    python3 scripts/live_eval.py --models claude-haiku-5-5,claude-sonnet-5-5 --max-cost 3

Free, on this computer (needs the Ollama app and a downloaded model):
    python3 scripts/live_eval.py --backend ollama --list-models
    python3 scripts/live_eval.py --backend ollama --models <model> --limit 5    # quick trial
    python3 scripts/live_eval.py --backend ollama --models <model>

Each model codes the 100 reports through the same agent loop as a full run
(code -> validate -> retry with feedback). Its labels are then compared with the
blinded manual review and, for context, with the two earlier AI runs from catheter-pms-ai
(rules v1.1 and v1.2). Tokens, cost and time are recorded for every API call.

Writes to outputs/live/:
    labels_<model>.csv      one row per report (plus attempts and status)
    calls_<model>.csv       one row per API call (tokens, cost, seconds)
    live_eval.md            the comparison report
"""
import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config, db, evaluate, validator          # noqa: E402
from agent.agent import PMSAgent                             # noqa: E402
from agent.coders import (BudgetExceeded, ClaudeCoder, OllamaCoder, list_ollama_models,  # noqa: E402
                          report_text)

MANUAL = config.DATA_DIR / "manual_review_100.csv"
BASELINES = {"Earlier AI run, rules v1.1": config.DATA_DIR / "baseline_labels_v1_1_100.csv",
             "Earlier AI run, rules v1.2": config.DATA_DIR / "baseline_labels_v1_2_100.csv"}


def review_reports():
    """The 100 manually reviewed reports, as dicts the coder accepts."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    db.load_reports(con)
    ids = list(evaluate.load_labels(MANUAL))
    rows = {r["report_number"]: dict(r) for r in con.execute(
        "SELECT * FROM reports WHERE report_number IN (%s)" % ",".join("?" * len(ids)), ids)}
    missing = [i for i in ids if i not in rows]
    if missing:
        sys.exit(f"{len(missing)} reviewed reports are missing from data/maude_reports.csv")
    return [rows[i] for i in ids]


def estimate(models, reports, backend="anthropic"):
    """Rough cost before anything is spent: about 4 characters per token."""
    rules_tokens = (len(config.RULES_FILE.read_text()) + 2500) / 4    # rules + instructions + tool schema
    report_tokens = sum(len(report_text(r)) for r in reports) / 4
    lines = [f"Reports: {len(reports)}; system prompt ~{rules_tokens:,.0f} tokens (cached after the first call); "
             f"reports ~{report_tokens / len(reports):,.0f} tokens each on average", ""]
    if backend == "ollama":
        return "\n".join(lines + [f"  {m}: free (runs on this computer); expect roughly 5-30 seconds per report"
                                    for m in models])
    total = 0.0
    for m in models:
        inp, write, read, out = config.PRICES[m]
        cost = (rules_tokens * write + (len(reports) - 1) * rules_tokens * read + report_tokens * inp
                + len(reports) * config.EST_OUTPUT_TOKENS * out) / 1e6
        cost *= 1.15                                                    # allowance for retries
        total += cost
        lines.append(f"  {m:<22} about ${cost:.2f}")
    lines += ["", f"  Total about ${total:.2f}. A full 300-report agent run costs about 3x the per-model figure."]
    return "\n".join(lines)


def list_models(backend="anthropic"):
    config.load_env()
    if backend == "ollama":
        try:
            names = list_ollama_models()
        except OSError as exc:
            sys.exit(f"Cannot reach Ollama: is the Ollama app running? ({exc})")
        print("\n".join(names) if names else "No models downloaded yet: run  ollama pull <model>")
        return
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("Put ANTHROPIC_API_KEY in .env first.")
    req = urllib.request.Request("https://api.anthropic.com/v1/models?limit=100",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        for m in json.loads(resp.read())["data"]:
            priced = "priced" if m["id"] in config.PRICES else "no price in config"
            print(f"{m['id']:<32} {m.get('display_name', ''):<24} {priced}")


def run_model(model, reports, max_cost, coder_factory=ClaudeCoder, verbose=False):
    """Code the reports with one model through the normal agent loop (on a scratch database)."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    db.load_reports(con)
    coder = coder_factory(model=model, max_cost=max_cost)
    if not reports:
        return {}, {}, coder, {"coded": 0, "retried": 0, "rejected": 0, "errors": 0, "routed": 0}
    agent = PMSAgent(con, coder)
    for k, r in enumerate(reports, 1):
        t0 = time.perf_counter()
        try:
            label = agent.code_one(r)
        except BudgetExceeded as exc:
            agent.stats["stopped"] = str(exc)
            break
        if label is not None:
            agent.store(r, label)
        if verbose:
            last = con.execute("SELECT outcome, detail FROM audit_log ORDER BY rowid DESC LIMIT 1").fetchone()
            what = f"{label['primary_fm']} {label['severity']}" if label else f"{last[0]}: {(last[1] or '')[:80]}"
            print(f"  [{k}/{len(reports)}] {r['report_number']}  {what}  ({time.perf_counter() - t0:.1f} s)",
                  flush=True)
    labels = {row["report_number"]: dict(row) for row in con.execute("SELECT * FROM labels")}
    attempts = {}
    for c in coder.calls:
        attempts[c["report_number"]] = max(attempts.get(c["report_number"], 0), c["attempt"])
    return labels, attempts, coder, agent.stats


def safe_name(model):
    """Model ids such as granite4.2:8b contain ':', which Windows does not allow in file names."""
    return "".join(c if c.isalnum() or c in "-._" else "-" for c in model)


def write_outputs(model, reports, labels, attempts, coder, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    model = safe_name(model)
    with open(out_dir / f"labels_{model}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["report_number"] + evaluate.FIELDS + ["confidence", "quote", "note", "attempts", "status"])
        for r in reports:
            rid = r["report_number"]
            lab = labels.get(rid)
            if lab is None:
                status = "not coded" if rid not in attempts else "rejected or error"
                w.writerow([rid] + [""] * (len(evaluate.FIELDS) + 3) + [attempts.get(rid, 0), status])
                continue
            vals = [lab["primary_fm"], lab["secondary_fm"] or "none", lab["phase"], lab["severity"],
                    lab["contributor"], "Y" if lab["retained_fragment"] else "N",
                    "Y" if lab["user_harm"] else "N"]
            w.writerow([rid] + vals + [lab["confidence"], lab["quote"], lab["note"],
                                       attempts.get(rid, 0), "coded"])
    with open(out_dir / f"calls_{model}.csv", "w", newline="", encoding="utf-8") as fh:
        if coder.calls:
            w = csv.DictWriter(fh, fieldnames=list(coder.calls[0]))
            w.writeheader()
            w.writerows(coder.calls)


def pct(x):
    return f"{100 * x:.0f}%"


def report_md(results, manual, n_reports, low_conf=None):
    """results: list of (name, labels_dict, stats or None, usage or None).
    low_conf: {name: report numbers the model marked low confidence} (these are routed to review)."""
    names = [r[0] for r in results]
    comps = {name: evaluate.compare(manual, labels) for name, labels, *_ in results}
    lines = ["# Live evaluation against the blinded manual review", "",
             f"Run {dt.datetime.now():%Y-%m-%d %H:%M}. Reference: the manual review of {n_reports} reports "
             "(coded blind, before seeing any AI label). Rules v" + config.RULES_VERSION + " for the live runs.", "",
             "## Agreement with the manual review (exact agreement, Cohen's kappa)", "",
             "| Field | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for f in evaluate.FIELDS:
        lines.append(f"| {evaluate.FIELD_NAMES[f]} | " + " | ".join(
            f"{pct(comps[n][f]['agreement'])} ({comps[n][f]['kappa']:.2f})" for n in names) + " |")
    lines.append("| Severity within one level | " + " | ".join(pct(comps[n]["severity_within_one"]) for n in names) + " |")
    lines.append("| All seven fields identical | " + " | ".join(pct(comps[n]["all_fields"]) for n in names) + " |")
    lines.append("| Reports scored | " + " | ".join(str(comps[n]["n"]) for n in names) + " |")
    low_conf = low_conf or {}
    catch = {name: evaluate.review_catch(manual, labels, low_conf.get(name, set()))
             for name, labels, *_ in results}
    lines += ["", "## Safety check: would the serious cases still reach a person?", "",
              "Reports whose manual coding triggers human review (severity S3 or worse, a retained fragment "
              "or harm to the user), and how many of them each model's labels would also send to review "
              "(its own S3+, fragment, user-harm or low-confidence flags).", "",
              "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names),
              "| Serious cases caught | " + " | ".join(
                  f"{catch[n]['caught']} of {catch[n]['should']} ({pct(catch[n]['caught'] / catch[n]['should'])})"
                  if catch[n]["should"] else "-" for n in names) + " |",
              "| Reports sent to review in total | " + " | ".join(str(catch[n]["routed_total"]) for n in names) + " |"]
    live = [r for r in results if r[3] is not None]
    if live:
        lines += ["", "## Cost, speed and the agent loop", "",
                  "| Model | Reports coded | Retries | Rejected | Errors | Sent to review | API calls | "
                  "Cost (USD) | Cost per report | Seconds per call |", "|---|---|---|---|---|---|---|---|---|---|"]
        for name, labels, stats, usage in live:
            per = usage["cost_usd"] / max(len(labels), 1)
            cost, per_s = ((f"{usage['cost_usd']:.3f}", f"{per:.4f}") if not name.startswith("Local")
                           else ("0 (local)", "0"))
            lines.append(f"| {name} | {stats['coded']} | {stats['retried']} | {stats['rejected']} | "
                         f"{stats['errors']} | {stats['routed']} | {usage['api_calls']} | "
                         f"{cost} | {per_s} | {usage['mean_seconds_per_call']} |")
            if stats.get("stopped"):
                lines.append(f"\nRun with {name} stopped early: {stats['stopped']}")
        lines += ["", "Token totals: " + "; ".join(
            f"{u['model']}: {u['input_tokens']:,} input, {u['cache_read_tokens']:,} read from cache, "
            f"{u['cache_write_tokens']:,} written to cache, {u['output_tokens']:,} output"
            for _, _, _, u in live)]
        lines += ["", "## Where the new runs disagree with the manual review (severity and failure mode)", ""]
        for name, labels, *_ in live:
            for f in ("primary_fm", "severity"):
                d = evaluate.disagreements(manual, labels, f)
                shown = ", ".join(f"{i} ({m} vs {a})" for i, m, a in d[:15])
                lines.append(f"- **{name}, {evaluate.FIELD_NAMES[f].lower()}** ({len(d)}): manual vs AI. {shown}"
                             + (" ..." if len(d) > 15 else ""))
    lines += ["", "## How to read this", "",
              "- The manual review is one reviewer's coding, not ground truth; disagreements need reading, "
              "not just counting.",
              "- The earlier runs coded reports inside a chat session; the new runs use fixed settings "
              "(temperature 0 for local models), so they are the repeatable result.",
              "- Local token counts are prompt tokens Ollama actually processed; text it reused from the "
              "previous call is not counted again.",
              "- Kappa corrects for agreement expected by chance: above 0.80 almost perfect, 0.61-0.80 "
              "substantial, 0.41-0.60 moderate."]
    return "\n".join(lines) + "\n"


def rescore(live_dir=None):
    """Rebuild the comparison report from files saved by earlier runs."""
    live_dir = Path(live_dir or config.LIVE_DIR)
    label_files = sorted(live_dir.glob("labels_*.csv"))
    if not label_files:
        sys.exit(f"No labels_*.csv in {live_dir}")
    runs = []
    for f in label_files:
        stem = f.stem[len("labels_"):]
        with open(f, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["status"] == "coded"]
        calls_f = live_dir / f"calls_{stem}.csv"
        calls = list(csv.DictReader(open(calls_f, encoding="utf-8"))) if calls_f.exists() else []
        model = calls[0]["model"] if calls else stem          # the real id, e.g. granite4.2:8b
        local = all(float(c["cost_usd"]) == 0 for c in calls)
        name = f"{'Local' if local else 'Live'}: {model}"
        attempts = {}
        for c in calls:
            attempts[c["report_number"]] = max(attempts.get(c["report_number"], 0), int(c["attempt"]))
        n = len(calls)
        tot = lambda k: sum(float(c[k]) for c in calls)
        usage = {"model": model, "api_calls": n, "input_tokens": int(tot("input_tokens")),
                 "cache_write_tokens": int(tot("cache_write_tokens")), "cache_read_tokens": int(tot("cache_read_tokens")),
                 "output_tokens": int(tot("output_tokens")), "cost_usd": round(tot("cost_usd"), 4),
                 "mean_seconds_per_call": round(tot("seconds") / n, 2) if n else 0}
        labels = {r["report_number"]: {k: evaluate.norm(k, r[k]) for k in evaluate.FIELDS} for r in rows}
        stats = {"coded": len(rows), "retried": sum(v - 1 for v in attempts.values()),
                 "rejected": 0, "errors": len(attempts) - len(rows),
                 "routed": sum(evaluate.needs_review(l) or r["confidence"] == "low"
                               for l, r in zip(labels.values(), rows))}
        runs.append((name, labels, stats, usage, {r["report_number"] for r in rows if r["confidence"] == "low"}))
    ids = set().union(*(set(r[1]) for r in runs))
    manual = {k: v for k, v in evaluate.load_labels(MANUAL).items() if k in ids}
    results = [(name, {k: v for k, v in evaluate.load_labels(path).items() if k in ids}, None, None)
               for name, path in BASELINES.items()] + [r[:4] for r in runs]
    path = live_dir / "live_eval.md"
    path.write_text(report_md(results, manual, len(manual), {r[0]: r[4] for r in runs}))
    print(f"Report: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic",
                    help="anthropic = paid API; ollama = free local model on this computer")
    ap.add_argument("--models", help="comma-separated model ids (default: Haiku and Sonnet for anthropic)")
    ap.add_argument("--max-cost", type=float, default=config.DEFAULT_MAX_COST,
                    help="USD cap for each model (default %(default)s)")
    ap.add_argument("--limit", type=int, help="only the first N reviewed reports (for a cheap trial)")
    ap.add_argument("--dry-run", action="store_true", help="print the cost estimate and stop")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--rescore", action="store_true",
                    help="rebuild live_eval.md from the saved labels_*.csv and calls_*.csv (no model calls)")
    a = ap.parse_args()

    if a.list_models:
        return list_models(a.backend)
    if a.rescore:
        return rescore()
    if not a.models and a.backend == "ollama":
        sys.exit("Name the local model: --models <name>  (see --list-models)")
    models = [m.strip() for m in (a.models or "claude-haiku-5-5,claude-sonnet-5-5").split(",") if m.strip()]
    if a.backend == "anthropic":
        unknown = [m for m in models if m not in config.PRICES]
        if unknown:
            sys.exit(f"No price in config.PRICES for: {', '.join(unknown)}")
    factory = ClaudeCoder if a.backend == "anthropic" else OllamaCoder
    reports = review_reports()[:a.limit] if a.limit else review_reports()
    print(estimate(models, reports, a.backend))
    if a.dry_run:
        return

    ids = {r["report_number"] for r in reports}
    manual = {k: v for k, v in evaluate.load_labels(MANUAL).items() if k in ids}
    results = [(name, {k: v for k, v in evaluate.load_labels(path).items() if k in ids}, None, None)
               for name, path in BASELINES.items()]
    low_conf = {}
    for m in models:
        cap = f" (cap ${a.max_cost:.2f})" if a.backend == "anthropic" else " (local, free)"
        print(f"\nCoding {len(reports)} reports with {m}{cap} ...")
        labels, attempts, coder, stats = run_model(m, reports, a.max_cost, factory, verbose=True)
        write_outputs(m, reports, labels, attempts, coder, config.LIVE_DIR)
        live = {rid: {f: evaluate.norm(f, v) for f, v in zip(
            evaluate.FIELDS, [lab["primary_fm"], lab["secondary_fm"] or "none", lab["phase"], lab["severity"],
                              lab["contributor"], "Y" if lab["retained_fragment"] else "N",
                              "Y" if lab["user_harm"] else "N"])} for rid, lab in labels.items()}
        low_conf[f"{'Live' if a.backend == 'anthropic' else 'Local'}: {m}"] = {
            rid for rid, lab in labels.items() if lab["confidence"] == "low"}
        usage = coder.usage_summary()
        print(f"  coded {stats['coded']}, retries {stats['retried']}, rejected {stats['rejected']}, "
              f"errors {stats['errors']}; spent ${usage['cost_usd']:.3f}")
        prefix = "Live" if a.backend == "anthropic" else "Local"
        results.append((f"{prefix}: {m}", live, stats, usage))
    path = config.LIVE_DIR / "live_eval.md"
    path.write_text(report_md(results, manual, len(reports), low_conf))
    print(f"\nReport: {path}")


if __name__ == "__main__":
    main()
