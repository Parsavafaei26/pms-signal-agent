"""Checks a proposed label against the coding rules before it can enter the database."""
from . import config


def validate(label):
    """Return a list of problems; an empty list means the label is acceptable."""
    errors = []
    allowed = {
        "primary_fm": config.FM_CODES,
        "phase": config.PHASES,
        "severity": config.SEVERITIES,
        "contributor": config.CONTRIBUTORS,
        "confidence": config.CONFIDENCE,
        "retained_fragment": ["Y", "N"],
        "user_harm": ["Y", "N"],
    }
    for field, values in allowed.items():
        if label.get(field) not in values:
            errors.append(f"{field} must be one of {values}, got {label.get(field)!r}")
    sec = label.get("secondary_fm", "none")
    if sec != "none" and sec not in config.FM_CODES:
        errors.append(f"secondary_fm must be 'none' or one of FM01-FM13, got {sec!r}")
    if sec == label.get("primary_fm"):
        errors.append("secondary_fm must differ from primary_fm (use 'none')")
    if not (label.get("quote") or "").strip():
        errors.append("quote is required: copy the words from the report that support the primary code")
    # Consistency rule from the coding rules: FM08 is a defect found before or at insertion
    if label.get("primary_fm") == "FM08" and label.get("phase") not in ("P1", "P2"):
        errors.append("FM08 covers defects found before use: phase must be P1 or P2")
    return errors


def review_reasons(label):
    """Why a label must be checked by a person (empty = no mandatory review)."""
    reasons = []
    if label["severity"] in config.REVIEW_SEVERITIES:
        reasons.append(f"severity {label['severity']}")
    if label["retained_fragment"] == "Y":
        reasons.append("retained fragment")
    if label["user_harm"] == "Y":
        reasons.append("user harm")
    if label["confidence"] == "low":
        reasons.append("low confidence")
    return reasons
