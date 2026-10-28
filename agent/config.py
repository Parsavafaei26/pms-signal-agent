"""Fixed settings. Signal thresholds were set before the first run and are reported with every run."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "outputs" / "pms.db"
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
RULES_FILE = ROOT / "rules" / "coding_rules.md"

RULES_VERSION = "1.2"
MAX_RETRIES = 2              # extra attempts when a label fails validation

# Signal thresholds (pre-specified)
SIGNAL_PARAMS = {
    "min_count": 5,          # rising failure mode: at least 5 complaints in the current 4 quarters
    "ratio": 2.0,            # ... and at least double the previous 4 quarters
    "cluster_min": 3,        # keyword cluster: at least 3 complaints in one quarter
    # exploratory share check (added after the first run; reported separately)
    "share_points": 15,      # share of complaints up by at least 15 percentage points
    "share_min": 10,         # ... with at least 10 complaints in the current window
}

# Human review routing (from project 1 validation: the AI under-rated severity)
REVIEW_SEVERITIES = {"S3", "S4", "S5"}

FM_CODES = [f"FM{n:02d}" for n in range(1, 14)]
PHASES = ["P1", "P2", "P3", "P4", "P5"]
SEVERITIES = ["S1", "S2", "S3", "S4", "S5"]
CONTRIBUTORS = ["DEV", "USE", "PAT", "UNK"]
CONFIDENCE = ["high", "medium", "low"]


# ---------------------------------------------------------------- live (API) runs
def load_env(path=ROOT / ".env"):
    """Read KEY=value lines from .env into the environment (existing variables win).
    .env is in .gitignore: the API key never goes into the repository."""
    import os
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# USD per million tokens: (input, cache write 5 min, cache read, output).
# From the Claude API pricing page, October 2026. Check before a run; prices change.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
}
DEFAULT_MAX_COST = 3.00      # USD: a run stops before it spends more than this
EST_OUTPUT_TOKENS = 350      # per call, used only for the --dry-run estimate
LIVE_DIR = OUT_DIR / "live"
