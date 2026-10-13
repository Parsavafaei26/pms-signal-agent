"""Command line entry point.

    python3 run.py                       # fresh database, replay coder, full run
    python3 run.py --coder claude        # live coder (needs ANTHROPIC_API_KEY and ANTHROPIC_MODEL)
    python3 run.py --limit 10            # code only the first 10 queued reports
"""
import argparse
from agent import config, db, report
from agent.agent import PMSAgent
from agent.coders import ClaudeCoder, ReplayCoder


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coder", choices=["replay", "claude"], default="replay")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--keep-db", action="store_true", help="add to the existing database instead of rebuilding")
    a = ap.parse_args()

    if not a.keep_db and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    con = db.connect()
    db.init(con)
    n = db.load_reports(con)
    coder = ReplayCoder() if a.coder == "replay" else ClaudeCoder()
    agent = PMSAgent(con, coder)
    queue = db.uncoded_queue(con)
    print(f"Loaded {n} reports; {len(queue)} in the coding queue; coder {coder.name}")
    found = agent.run(queue, a.limit)
    q = report.write_review_queue(con)
    path = report.write_signal_report(con, agent, found)
    print(f"Coded {agent.stats['coded']}, retries {agent.stats['retried']}, rejected {agent.stats['rejected']}, "
          f"errors {agent.stats['errors']}; review queue {q}; signals {len(found)}")
    print(f"Report: {path.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
