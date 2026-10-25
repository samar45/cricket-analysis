"""Run log: every update / dry-run / health run writes one JSON file, data/runs/<run_id>.json (schema 1).

The file is the audit trail: each step with its seconds, each check with expected vs actual, and the before/after
fingerprints. It is written even when the run fails. The dashboard's health page reads these files.
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


class Step:
    def __init__(self):
        self.status, self.details = "pass", {}

    def skip(self, reason: str):
        self.status, self.details["reason"] = "skip", reason

    def fail(self, reason: str):
        self.status, self.details["reason"] = "fail", reason


class RunLog:
    def __init__(self, kind: str, db_path: Path, args: dict):
        self.dir = Path(db_path).parent / "runs"
        self.t0 = datetime.now()
        self.doc = {
            "schema": 1,
            "run_id": None,
            "kind": kind,
            "started": self.t0.isoformat(timespec="seconds"),
            "finished": None,
            "ok": False,
            "error": None,
            "db_path": str(db_path),
            "args": args,
            "steps": [],
            "checks": [],
            "new_by_competition": {},
            "skipped_events": [],
            "changed_matches": [],
            "freshness_before": {},
            "freshness_after": {},
            "fingerprint_before": {},
            "fingerprint_after": {},
            "golden": [],
            "swapped": False,
            "backup": None,
        }
        self.path: Path | None = None

    @contextmanager
    def step(self, name: str):
        """`with log.step("x") as s:` records status/seconds; an exception marks it failed and propagates."""
        s, t = Step(), time.monotonic()
        try:
            yield s
        except BaseException as e:
            s.status, s.details["error"] = "fail", f"{type(e).__name__}: {e}"
            raise
        finally:
            self.doc["steps"].append(
                {
                    "name": name,
                    "status": s.status,
                    "seconds": round(time.monotonic() - t, 2),
                    "details": s.details,
                }
            )

    def skip(self, name: str, reason: str):
        self.doc["steps"].append(
            {"name": name, "status": "skip", "seconds": 0.0, "details": {"reason": reason}}
        )

    def check(self, name, status, expected=None, actual=None, message=""):
        self.doc["checks"].append(
            {
                "name": name,
                "status": status,
                "expected": expected,
                "actual": actual,
                "message": message,
            }
        )

    def finish(self, ok: bool, error: str | None = None) -> Path:
        d = self.doc
        d["ok"], d["error"] = bool(ok), error
        d["finished"] = datetime.now().isoformat(timespec="seconds")
        self.dir.mkdir(parents=True, exist_ok=True)
        t = self.t0
        while (
            self.dir / f"{t:%Y%m%d-%H%M%S}.json"
        ).exists():  # two runs in one second: take the next free id
            t += timedelta(seconds=1)
        d["run_id"] = f"{t:%Y%m%d-%H%M%S}"
        self.path = self.dir / f"{d['run_id']}.json"
        self.path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        return self.path


def list_runs(db_path: Path, last: int = 10) -> list[dict]:
    """Newest-first summaries of logged runs next to db_path."""
    files = sorted((Path(db_path).parent / "runs").glob("*.json"), reverse=True)[:last]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]
