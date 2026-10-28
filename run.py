"""Command line entry point.

    python3 run.py                       # fresh database, replay coder, full run
    python3 run.py --coder claude        # live coder (needs ANTHROPIC_API_KEY and ANTHROPIC_MODEL, e.g. in .env)
    python3 run.py --coder claude --model claude-haiku-5-5 --max-cost 2
    python3 run.py --coder ollama --model <local model>   # free, on this computer via Ollama
    python3 run.py --limit 10            # code only the first 10 queued reports
"""
import argparse
import csv
import json
from agent import config, db, report
from agent.agent import PMSAgent
from agent.coders import ClaudeCoder, OllamaCoder, ReplayCoder


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coder", choices=["replay", "claude", "ollama"], default="replay")
    ap.add_argument("--model", help="live model id (default: ANTHROPIC_MODEL)")
    ap.add_argument("--max-cost", type=float, default=config.DEFAULT_MAX_COST,
                    help="USD cap for a live run (default %(default)s)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--keep-db", action="store_true", help="add to the existing database instead of rebuilding")
    a = ap.parse_args()

    if not a.keep_db and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    con = db.connect()
    db.init(con)
    n = db.load_reports(con)
    coder = {"replay": lambda: ReplayCoder(),
             "claude": lambda: ClaudeCoder(model=a.model, max_cost=a.max_cost),
             "ollama": lambda: OllamaCoder(model=a.model)}[a.coder]()
    agent = PMSAgent(con, coder)
    queue = db.uncoded_queue(con)
    print(f"Loaded {n} reports; {len(queue)} in the coding queue; coder {coder.name}")
    found = agent.run(queue, a.limit)
    # live runs write to outputs/live/ so the published replay outputs are kept for comparison
    out = config.OUT_DIR if a.coder == "replay" else config.LIVE_DIR
    out.mkdir(parents=True, exist_ok=True)
    q = report.write_review_queue(con, out / "review_queue.csv")
    path = report.write_signal_report(con, agent, found, out / "signal_report.md")
    print(f"Coded {agent.stats['coded']}, retries {agent.stats['retried']}, rejected {agent.stats['rejected']}, "
          f"errors {agent.stats['errors']}; review queue {q}; signals {len(found)}")
    print(f"Report: {path.relative_to(config.ROOT)}")
    if agent.stats.get("stopped"):
        print(f"Stopped early: {agent.stats['stopped']}")
    if isinstance(coder, (ClaudeCoder, OllamaCoder)):
        config.LIVE_DIR.mkdir(parents=True, exist_ok=True)
        usage = coder.usage_summary() | {"run_id": agent.run_id, "stats": agent.stats}
        (config.LIVE_DIR / "full_run_usage.json").write_text(json.dumps(usage, indent=2))
        if coder.calls:
            with open(config.LIVE_DIR / "full_run_calls.csv", "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(coder.calls[0]))
                w.writeheader()
                w.writerows(coder.calls)
        print(f"Live usage: {usage['api_calls']} model calls, ${usage['cost_usd']:.3f}, "
              f"{usage['mean_seconds_per_call']} s per call "
              f"(details in outputs/live/full_run_usage.json)")


if __name__ == "__main__":
    main()
