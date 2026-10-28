"""Agreement between two sets of labels, computed the same way as in catheter-pms-ai.

Exact agreement and unweighted Cohen's kappa per field, severity within one level,
and the share of reports where all seven fields match.
"""
import csv
from collections import Counter

FIELDS = ["primary_fm", "secondary_fm", "phase", "severity", "contributor",
          "retained_fragment", "user_harm"]
FIELD_NAMES = {"primary_fm": "Primary failure mode", "secondary_fm": "Secondary failure mode",
               "phase": "Phase of use", "severity": "Severity", "contributor": "Likely contributor",
               "retained_fragment": "Retained fragment", "user_harm": "User harm"}


def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def norm(field, value):
    value = (value or "").strip()
    if field == "secondary_fm" and value in ("", "None", "null"):
        return "none"
    return value


def load_labels(path):
    with open(path, encoding="utf-8") as fh:
        return {r["report_number"]: {f: norm(f, r.get(f)) for f in FIELDS} for r in csv.DictReader(fh)}


def compare(reference, test):
    """reference, test: {report_number: {field: value}}. Only reports in both are scored."""
    ids = sorted(set(reference) & set(test))
    out = {"n": len(ids)}
    for f in FIELDS:
        a = [reference[i][f] for i in ids]
        b = [test[i][f] for i in ids]
        out[f] = {"agreement": sum(x == y for x, y in zip(a, b)) / len(ids) if ids else float("nan"),
                  "kappa": kappa(a, b)}
    sev = [(reference[i]["severity"], test[i]["severity"]) for i in ids]
    within = [abs(int(x[1:]) - int(y[1:])) <= 1 for x, y in sev if x[1:].isdigit() and y[1:].isdigit()]
    out["severity_within_one"] = sum(within) / len(within) if within else float("nan")
    out["all_fields"] = (sum(all(reference[i][f] == test[i][f] for f in FIELDS) for i in ids) / len(ids)
                         if ids else float("nan"))
    return out


def disagreements(reference, test, field):
    return [(i, reference[i][field], test[i][field])
            for i in sorted(set(reference) & set(test)) if reference[i][field] != test[i][field]]


def needs_review(label):
    """The review triggers that can be read from the seven coded fields (see validator.review_reasons):
    severity S3 or worse, a retained fragment, or harm to the user."""
    return label["severity"] in ("S3", "S4", "S5") or label["retained_fragment"] == "Y" or label["user_harm"] == "Y"


def review_catch(reference, test, low_confidence=()):
    """Of the reports the reference coding would send to a person, how many would the test labels
    also send? low_confidence: report numbers the model marked low confidence (also routed)."""
    ids = sorted(set(reference) & set(test))
    should = [i for i in ids if needs_review(reference[i])]
    caught = [i for i in should if needs_review(test[i]) or i in low_confidence]
    return {"should": len(should), "caught": len(caught),
            "missed": [i for i in should if i not in caught],
            "routed_total": sum(needs_review(test[i]) or i in low_confidence for i in ids)}
