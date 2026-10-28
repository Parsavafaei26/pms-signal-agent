"""Coders turn one report into a proposed label.

ReplayCoder  - returns labels already produced by Claude in project 1 (catheter-pms-ai), so the
               whole pipeline can run and be tested without an API key.
ClaudeCoder  - calls the Anthropic Messages API with the coding rules and a forced tool call,
               so the answer comes back as structured fields. Needs ANTHROPIC_API_KEY and
               ANTHROPIC_MODEL (a current model id from the Anthropic documentation).
"""
import csv
import json
import os
import time
import urllib.error
import urllib.request
from . import config

LABEL_FIELDS = ["primary_fm", "secondary_fm", "phase", "severity", "contributor",
                "retained_fragment", "user_harm", "complaint_group", "confidence", "quote", "note"]

RECORD_LABEL_TOOL = {
    "name": "record_label",
    "description": "Record the coded label for one adverse event report, following the coding rules.",
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_fm": {"type": "string", "enum": config.FM_CODES},
            "secondary_fm": {"type": "string", "enum": ["none"] + config.FM_CODES},
            "phase": {"type": "string", "enum": config.PHASES},
            "severity": {"type": "string", "enum": config.SEVERITIES},
            "contributor": {"type": "string", "enum": config.CONTRIBUTORS},
            "retained_fragment": {"type": "string", "enum": ["Y", "N"]},
            "user_harm": {"type": "string", "enum": ["Y", "N"]},
            "confidence": {"type": "string", "enum": config.CONFIDENCE},
            "quote": {"type": "string", "description": "Short quote from the report supporting the primary code"},
            "note": {"type": "string", "description": "One sentence explaining the key reason"},
        },
        "required": ["primary_fm", "secondary_fm", "phase", "severity", "contributor",
                     "retained_fragment", "user_harm", "confidence", "quote", "note"],
    },
}


def report_text(report):
    return (f"Report number: {report['report_number']}\n"
            f"Event type: {report['event_type']}\nDevice: {report['brand_name']}\n"
            f"FDA device problem codes (hints only): {report['fda_device_problems']}\n"
            f"FDA patient problem codes (hints only): {report['fda_patient_problems']}\n\n"
            f"EVENT DESCRIPTION:\n{report['event_description']}\n\n"
            f"MANUFACTURER NARRATIVE:\n{report['manufacturer_narrative']}")


class ReplayCoder:
    name = "replay:v1.1"
    rules_version = "1.1"

    def __init__(self, path=None):
        path = path or config.DATA_DIR / "replay_labels_v1_1.csv"
        self.labels = {}
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r["quote"] = r.pop("supporting_quote", r.get("quote", ""))
                self.labels[r["report_number"]] = r

    def code(self, report, feedback=None):
        lab = self.labels.get(report["report_number"])
        if lab is None:
            raise LookupError("no stored label for this report (replay mode can only code the project 1 sample)")
        return {k: lab.get(k, "") for k in LABEL_FIELDS + ["voided"]} | {
            "voided": "VOIDED" in lab.get("note", "")}


class BudgetExceeded(RuntimeError):
    """Raised before an API call that would start once the spending cap is reached."""


def price_of(model, usage):
    """Cost in USD of one response, from its usage block. None if the model has no price entry."""
    p = config.PRICES.get(model)
    if p is None:
        return None
    inp, write, read, out = p
    return (usage.get("input_tokens", 0) * inp
            + usage.get("cache_creation_input_tokens", 0) * write
            + usage.get("cache_read_input_tokens", 0) * read
            + usage.get("output_tokens", 0) * out) / 1e6


class ClaudeCoder:
    """Live coder. Records tokens, cost and time for every call, and stops at a spending cap.

    The system prompt (instructions + coding rules) is identical for every report, so it is
    sent with prompt caching: after the first call it is read from cache at a fraction of the price.
    """
    rules_version = config.RULES_VERSION
    url = "https://api.anthropic.com/v1/messages"
    RETRY_STATUS = {429, 500, 502, 503, 529}

    def __init__(self, api_key=None, model=None, opener=urllib.request.urlopen,
                 max_cost=config.DEFAULT_MAX_COST, sleep=time.sleep, rules_file=None):
        config.load_env()
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("ANTHROPIC_MODEL")
        if not self.api_key or not self.model:
            raise RuntimeError("Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL (in .env or the environment) "
                               "to use the live coder.")
        if self.model not in config.PRICES:
            raise RuntimeError(f"No price for {self.model!r} in config.PRICES: add it before a paid run.")
        self.name = f"claude:{self.model}"
        self.opener, self.sleep, self.max_cost = opener, sleep, max_cost
        rules = (rules_file or config.RULES_FILE).read_text()
        self.system = [{"type": "text", "cache_control": {"type": "ephemeral"}, "text": (
            "You code medical device adverse event reports for post-market surveillance. "
            "Apply these coding rules exactly. Base every answer on the report text; "
            "FDA problem codes are hints only. Never decide reportability.\n\n" + rules)}]
        self._messages, self._last_tool_id = {}, {}
        self.calls = []          # one dict per API call: report, attempt, tokens, cost, seconds
        self.spent = 0.0

    def _post(self, body):
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        for attempt in range(5):
            try:
                with self.opener(req, timeout=120) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code not in self.RETRY_STATUS or attempt == 4:
                    raise RuntimeError(f"API error {exc.code}: {exc.read()[:300]!r}") from None
                wait = float(exc.headers.get("retry-after") or 2 ** (attempt + 1))
                self.sleep(min(wait, 60))

    def _call(self, rid, messages):
        if self.spent >= self.max_cost:
            raise BudgetExceeded(f"spending cap of ${self.max_cost:.2f} reached (spent ${self.spent:.4f})")
        body = {"model": self.model, "max_tokens": 1024, "system": self.system,
                "tools": [RECORD_LABEL_TOOL],
                "tool_choice": {"type": "tool", "name": "record_label"},
                "messages": messages}
        t0 = time.perf_counter()
        resp = self._post(body)
        usage = resp.get("usage", {})
        cost = price_of(self.model, usage) or 0.0
        self.spent += cost
        self.calls.append({
            "report_number": rid, "model": self.model, "attempt": len(messages) // 2 + 1,
            "input_tokens": usage.get("input_tokens", 0),
            "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cost_usd": round(cost, 6), "seconds": round(time.perf_counter() - t0, 2)})
        return resp

    def usage_summary(self):
        n = len(self.calls)
        tot = lambda k: sum(c[k] for c in self.calls)
        return {"model": self.model, "api_calls": n, "reports": len({c["report_number"] for c in self.calls}),
                "input_tokens": tot("input_tokens"), "cache_write_tokens": tot("cache_write_tokens"),
                "cache_read_tokens": tot("cache_read_tokens"), "output_tokens": tot("output_tokens"),
                "cost_usd": round(self.spent, 4),
                "mean_seconds_per_call": round(tot("seconds") / n, 2) if n else 0}

    def code(self, report, feedback=None):
        """feedback = validator errors from the previous attempt; they are sent back as a tool error."""
        rid = report["report_number"]
        if feedback is None:
            messages = [{"role": "user", "content": report_text(report)}]
        else:
            messages = self._messages[rid]
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": self._last_tool_id[rid], "is_error": True,
                "content": "The label was rejected by the validator:\n- " + "\n- ".join(feedback)
                           + "\nRe-read the rules and record a corrected label."}]})
        resp = self._call(rid, messages)
        block = next(b for b in resp["content"] if b["type"] == "tool_use")
        messages.append({"role": "assistant", "content": resp["content"]})
        self._messages[rid] = messages
        self._last_tool_id[rid] = block["id"]
        label = dict(block["input"])
        label["complaint_group"] = rid      # grouping repeat reports is a separate, human step
        label["voided"] = False
        return label


INSTRUCTIONS = ("You code medical device adverse event reports for post-market surveillance. "
                "Apply these coding rules exactly. Base every answer on the report text; "
                "FDA problem codes are hints only. Never decide reportability.\n\n")


class OllamaCoder:
    """Free local coder: an open-source model running on this computer through Ollama.

    Nothing leaves the computer and there is no cost. Ollama's structured outputs force the reply
    into the same JSON schema as the Claude tool call, so the validator, retry loop and scoring are
    unchanged. Temperature 0 and a fixed seed make runs repeatable.
    """
    rules_version = config.RULES_VERSION

    def __init__(self, model=None, host=None, opener=urllib.request.urlopen, num_ctx=8192,
                 num_predict=700, timeout=300, rules_file=None, **_ignored):
        config.load_env()
        self.model = model or os.environ.get("OLLAMA_MODEL")
        if not self.model:
            raise RuntimeError("Choose a local model: --model <name> or OLLAMA_MODEL in .env")
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.name = f"ollama:{self.model}"
        # num_predict caps the reply length: with a forced JSON format some local models keep
        # writing whitespace and never stop, so an uncapped call can hang for many minutes
        self.opener, self.num_ctx, self.num_predict, self.timeout = opener, num_ctx, num_predict, timeout
        think = os.environ.get("OLLAMA_THINK", "").strip().lower()
        self.think = {"true": True, "false": False}.get(think)    # unset = model default
        rules = (rules_file or config.RULES_FILE).read_text()
        self.system = (INSTRUCTIONS + rules + "\n\nReply with one JSON object only, with these fields: "
                       + ", ".join(RECORD_LABEL_TOOL["input_schema"]["required"]) + ".")
        self.schema = RECORD_LABEL_TOOL["input_schema"]
        self._messages = {}
        self.calls = []
        self.spent = 0.0
        self.max_cost = float("inf")

    def _call(self, rid, messages):
        body = {"model": self.model, "stream": False, "format": self.schema,
                "messages": [{"role": "system", "content": self.system}] + messages,
                "options": {"temperature": 0, "seed": 42, "num_ctx": self.num_ctx,
                            "num_predict": self.num_predict}}
        if self.think is not None:
            body["think"] = self.think
        req = urllib.request.Request(self.host + "/api/chat", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json"})
        t0 = time.perf_counter()
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read())
        except TimeoutError:
            raise RuntimeError(f"no reply within {self.timeout} s") from None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Ollama error {exc.code}: {exc.read()[:300]!r}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach Ollama at {self.host}: is the Ollama app running? ({exc})") from None
        n_prompt = out.get("prompt_eval_count", 0)
        if n_prompt >= self.num_ctx:
            raise RuntimeError(f"prompt of {n_prompt} tokens filled the {self.num_ctx}-token context: "
                               "raise num_ctx, or the rules may have been cut off")
        self.calls.append({
            "report_number": rid, "model": self.model, "attempt": len(messages) // 2 + 1,
            "input_tokens": n_prompt, "cache_write_tokens": 0, "cache_read_tokens": 0,
            "output_tokens": out.get("eval_count", 0), "cost_usd": 0.0,
            "seconds": round(time.perf_counter() - t0, 2)})
        if out.get("done_reason") == "length":
            self._save_debug(rid, out)
            raise RuntimeError(f"reply cut off at {self.num_predict} tokens (the model did not finish the JSON)")
        return out["message"]["content"]

    usage_summary = ClaudeCoder.usage_summary

    def _save_debug(self, rid, out):
        """Keep the raw reply of a failed call so the cause can be read (outputs/live/debug/)."""
        d = config.LIVE_DIR / "debug"
        d.mkdir(parents=True, exist_ok=True)
        msg = out.get("message", {})
        (d / f"{rid}.json").write_text(json.dumps({
            "model": self.model, "done_reason": out.get("done_reason"),
            "eval_count": out.get("eval_count"), "thinking": msg.get("thinking"),
            "content": msg.get("content")}, indent=2))

    def code(self, report, feedback=None):
        rid = report["report_number"]
        if feedback is None:
            messages = [{"role": "user", "content": report_text(report)}]
        else:
            messages = self._messages[rid]
            messages.append({"role": "user", "content": "The label was rejected by the validator:\n- "
                             + "\n- ".join(feedback) + "\nRe-read the rules and reply with a corrected label."})
        content = self._call(rid, messages)
        messages.append({"role": "assistant", "content": content})
        self._messages[rid] = messages
        try:
            label = json.loads(content)
        except json.JSONDecodeError:
            raise RuntimeError(f"model reply was not valid JSON: {content[:200]!r}") from None
        label["complaint_group"] = rid
        label["voided"] = False
        return label


def list_ollama_models(host=None, opener=urllib.request.urlopen):
    config.load_env()
    host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    with opener(host + "/api/tags", timeout=10) as resp:
        return [m["name"] for m in json.loads(resp.read()).get("models", [])]
