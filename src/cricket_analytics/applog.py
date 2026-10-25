"""Error log + ask log. Files live in $CRICKET_LOG_DIR (default <repo>/logs):

    errors.log  rotating text log (5 x 1 MB), one line per caught error, tagged with an error id like E-20261025-1432-ab12
    ask.jsonl   one JSON line per ask() call, plus feedback lines ({"type": "feedback", "ask_id": ...})

Only params, page and module names are logged, never keys or tokens. Logging must never break the app: all writes swallow OSError.
"""

import datetime as dt
import json
import logging
import os
import secrets
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

_logger = logging.getLogger("cricket.errors")
_logger.propagate = False
_logger.setLevel(logging.INFO)


def log_dir() -> Path:
    d = Path(os.environ.get("CRICKET_LOG_DIR") or Path(__file__).resolve().parents[2] / "logs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _short(v, n: int = 2000):
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "...[truncated]"


def new_id(prefix: str = "E") -> str:
    return f"{prefix}-{dt.datetime.now():%Y%m%d-%H%M}-{secrets.token_hex(2)}"


def _handler() -> None:
    path = str(log_dir() / "errors.log")
    for h in _logger.handlers:
        if getattr(h, "baseFilename", None) == str(Path(path).resolve()):
            return
    for h in list(_logger.handlers):   # the log folder changed (tests): swap the file
        _logger.removeHandler(h)
        h.close()
    h = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=4, encoding="utf-8")   # 5 files x 1 MB
    h.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(h)


def log_error(where: str, exc: BaseException, **ctx) -> str:
    """Write one error entry (with traceback) and return its id. A second call for the same exception reuses the id."""
    eid = getattr(exc, "error_id", None) or new_id()
    try:
        exc.error_id = eid
    except Exception:  # noqa: BLE001, some exceptions refuse attributes
        pass
    try:
        _handler()
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        _logger.error("%s | %s | %s: %s | ctx=%s\n%s", eid, where, type(exc).__name__, exc, _short(ctx, 500), tb)
    except OSError:
        pass
    return eid


def log_note(where: str, message: str, **ctx) -> str:
    """An error-ish event without an exception (e.g. the model returned no tool)."""
    eid = new_id()
    try:
        _handler()
        _logger.warning("%s | %s | %s | ctx=%s", eid, where, message, _short(ctx, 500))
    except OSError:
        pass
    return eid


# ------------------------------------------------------------------ ask log
def _append(entry: dict) -> None:
    try:
        with open(log_dir() / "ask.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except OSError:
        pass


def log_ask(entry: dict) -> dict:
    entry = {"type": "ask", "ts": dt.datetime.now().isoformat(timespec="seconds"), **entry}
    for k, n in (("raw", 2000), ("answer", 500)):
        if entry.get(k):
            entry[k] = _short(entry[k], n)
    _append(entry)
    return entry


def log_feedback(ask_id: str, rating: str, comment: str = "", expected_module: str | None = None) -> dict:
    """rating: 'up' or 'down'."""
    e = {"type": "feedback", "ts": dt.datetime.now().isoformat(timespec="seconds"), "ask_id": ask_id,
         "rating": rating, "comment": comment.strip(), "expected_module": expected_module or None}
    _append(e)
    return e


def read_asks(last: int | None = None, bad_only: bool = False) -> list[dict]:
    """Ask lines with their latest feedback merged in as `rating`, `comment`, `expected_module`. Newest last."""
    p = log_dir() / "ask.jsonl"
    if not p.exists():
        return []
    asks, fb = [], {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "feedback":
            fb[e["ask_id"]] = e
        elif e.get("type") == "ask":
            asks.append(e)
    for a in asks:
        f = fb.get(a["id"], {})
        a["rating"], a["comment"], a["expected_module"] = f.get("rating"), f.get("comment"), f.get("expected_module")
    if bad_only:
        asks = [a for a in asks if a["rating"] == "down" or a["status"] in ("error", "no_tool")]
    return asks[-last:] if last else asks
