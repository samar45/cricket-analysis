"""Minimal CricketData.org (CricAPI) client. Key from env CRICAPI_KEY (never logged).

Every response is cached under data/external/cricapi/ (gitignored); cached calls are never re-fetched.
Each live call appends a line to data/external/cricapi/calls.log with endpoint, params and hits used.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

BASE = "https://api.cricapi.com/v1/"
CACHE = Path(__file__).resolve().parents[3] / "data" / "external" / "cricapi"


def _key() -> str:
    key = os.environ.get("CRICAPI_KEY")
    if not key:  # fall back to project .env
        env = CACHE.parents[2] / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("CRICAPI_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("CRICAPI_KEY not set (env or .env)")
    return key


def get(endpoint: str, **params) -> dict:
    """GET endpoint; returns parsed JSON. Cached by endpoint+params."""
    CACHE.mkdir(parents=True, exist_ok=True)
    tag = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]
    f = CACHE / f"{endpoint}_{tag}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = requests.get(BASE + endpoint, params={"apikey": _key(), **params}, timeout=30)
    data = r.json()
    f.write_text(json.dumps(data), encoding="utf-8")
    info = data.get("info", {})
    with (CACHE / "calls.log").open("a") as log:
        log.write(f"{time.strftime('%F %T')} {endpoint} {params} http={r.status_code} "
                  f"status={data.get('status')} hits={info.get('hitsToday')}/{info.get('hitsLimit')} "
                  f"used={info.get('hitsUsed')}\n")
    return data
