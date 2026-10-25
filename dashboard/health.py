"""Data health page: reads the run logs in data/runs/*.json (written by `cricket update` / `cricket health`).

Falls back to labelled sample logs (tests/fixtures/runs) when there are none. Read-only except for the action
buttons, which run the CLI in a separate process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("CRICKET_RUNS_DIR") or ROOT / "data" / "runs")
SAMPLE_DIR = ROOT / "tests" / "fixtures" / "runs"
ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}
RED, AMBER = "background-color: #5c1f1f", "background-color: #5c4a1a"


def load_runs(d: Path) -> list[dict]:
    """Newest first. An unreadable file becomes a row with `load_error` instead of raising."""
    runs = []
    for p in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(r, dict):
                raise ValueError("not a JSON object")
            r.setdefault("run_id", p.stem)
            r["_file"] = p.name
            runs.append(r)
        except (OSError, ValueError) as e:
            runs.append(
                {"run_id": p.stem, "load_error": f"{type(e).__name__}: {e}", "_file": p.name}
            )
    return runs


def _rows(r: dict, key: str) -> list[dict]:
    v = r.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _dicts(r: dict, key: str) -> dict:
    v = r.get(key)
    return v if isinstance(v, dict) else {}


def _status(r: dict) -> str:
    if r.get("load_error") or not r.get("ok"):
        return "fail"
    return "warn" if any(c.get("status") == "warn" for c in _rows(r, "checks")) else "pass"


def _summary_row(r: dict) -> dict:
    if r.get("load_error"):
        return {
            "run_id": r["run_id"],
            "kind": "?",
            "ok": "❌ unreadable",
            "new matches": "",
            "passed": "",
            "failed": "",
            "warned": "",
            "seconds": "",
            "swapped": "",
            "error": r["load_error"],
        }
    cs = [c.get("status") for c in _rows(r, "checks")]
    new = 0
    for v in _dicts(r, "new_by_competition").values():
        try:
            new += int(v.get("matches") or 0)
        except (TypeError, ValueError, AttributeError):
            pass
    secs = 0.0
    for s in _rows(r, "steps"):
        try:
            secs += float(s.get("seconds") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "run_id": r["run_id"],
        "kind": r.get("kind"),
        "ok": ICON[_status(r)],
        "new matches": new,
        "passed": cs.count("pass"),
        "failed": cs.count("fail"),
        "warned": cs.count("warn"),
        "seconds": round(secs, 1),
        "swapped": bool(r.get("swapped")),
        "error": r.get("error") or "",
    }


def _tint(row):
    colour = {"fail": RED, "warn": AMBER}.get(row.get("status"), "")
    return [colour] * len(row)


def _table(rows: list[dict], cols: list[str], tint: bool = True):
    if not rows:
        st.caption("Nothing recorded.")
        return
    df = pd.DataFrame(rows).reindex(columns=cols).fillna("").astype(str)
    st.dataframe(
        df.style.apply(_tint, axis=1) if tint and "status" in cols else df,
        hide_index=True,
        width="stretch",
    )


def _compare(before: dict, after: dict, fields: list[str]):
    """Before/after per competition; the cells of a field that differs are highlighted."""
    rows = []
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k), after.get(k)
        b, a = (b if isinstance(b, dict) else {}), (a if isinstance(a, dict) else {})
        row = {"competition": k}
        for f in fields:
            row[f"{f} before"], row[f"{f} after"] = b.get(f, ""), a.get(f, "")
        rows.append(row)
    if not rows:
        st.caption("Not recorded for this run.")
        return
    df = pd.DataFrame(rows).astype(str)

    def mark(row):
        return [
            ""
            if c == "competition"
            or row[f"{c.rsplit(' ', 1)[0]} before"] == row[f"{c.rsplit(' ', 1)[0]} after"]
            else AMBER
            for c in row.index
        ]

    st.dataframe(df.style.apply(mark, axis=1), hide_index=True, width="stretch")


def _detail(r: dict):
    if r.get("load_error"):
        st.error(f"Could not read {r['_file']}: {r['load_error']}")
        return
    if r.get("error"):
        st.error(f"Run error: {r['error']}")
    st.markdown("**Steps**")
    _table(_rows(r, "steps"), ["name", "status", "seconds"])
    st.markdown("**Checks**")
    _table(_rows(r, "checks"), ["name", "status", "expected", "actual", "message"])
    st.markdown("**Freshness (matches, latest date)**")
    _compare(_dicts(r, "freshness_before"), _dicts(r, "freshness_after"), ["matches", "latest"])
    st.markdown(
        "**Fingerprint (matches, balls, runs, wickets).** A highlighted cell means the data changed."
    )
    _compare(
        _dicts(r, "fingerprint_before"),
        _dicts(r, "fingerprint_after"),
        ["matches", "balls", "runs", "wickets"],
    )
    st.markdown("**Golden numbers** (known-good stats)")
    _table(_rows(r, "golden"), ["name", "expected", "actual", "status"])
    new = [
        {"competition": k, **v}
        for k, v in _dicts(r, "new_by_competition").items()
        if isinstance(v, dict)
    ]
    if new:
        st.markdown("**New matches**")
        _table(new, ["competition", "matches", "earliest", "latest"], tint=False)
    if _rows(r, "changed_matches"):
        st.markdown("**Matches whose numbers changed at Cricsheet**")
        _table(_rows(r, "changed_matches"), ["match_id", "reason"], tint=False)
    if _rows(r, "skipped_events"):
        st.markdown("**Skipped events** (not tracked; review for league renames)")
        _table(_rows(r, "skipped_events"), ["event", "match_type", "gender", "count"], tint=False)
    st.caption(
        f"Backup: {r.get('backup') or 'none'} | DB: {r.get('db_path')} | {r.get('started')} to {r.get('finished')}"
    )
    st.download_button(
        "Download run JSON",
        json.dumps({k: v for k, v in r.items() if k != "_file"}, indent=2),
        f"{r['run_id']}.json",
        "application/json",
        key=f"dl_{r['run_id']}",
    )


def _run_cli(*args: str):
    cmd = [sys.executable, "-m", "cricket_analytics.cli", *args]
    with st.spinner("Running: cricket " + " ".join(args)):
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
            out, code = (p.stdout + p.stderr).strip(), p.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            out, code = f"{type(e).__name__}: {e}", -1
    st.session_state["health_out"] = (" ".join(args), code, out)


def _actions():
    c1, c2, c3 = st.columns(3)
    if c1.button("Run health check", key="h_check"):
        _run_cli("health")
    if c2.button("Dry-run update", key="h_dry"):
        _run_cli("update", "--dry-run")
    with c3, st.expander("Real update (careful)"):
        st.warning(
            "This dashboard keeps the database open. On Windows the final file swap fails while it is open, "
            "and nothing is changed. Safe way: stop the dashboard, run `cricket update` in a terminal, "
            "then start the dashboard again (see docs/RUNBOOK.md)."
        )
        if st.checkbox("I understand, run it from here anyway", key="h_confirm") and st.button(
            "Run update", key="h_update"
        ):
            _run_cli("update")
    if "health_out" in st.session_state:
        cmd, code, out = st.session_state["health_out"]
        (st.success if code == 0 else st.error)(f"cricket {cmd}: exit code {code}")
        st.code(out or "(no output)")


def _db_cards() -> tuple[str, dict]:
    try:
        from cricket_analytics import api

        info = api.data_info()
        return str(info["db_modified"]), {
            c["competition"]: c["latest"] for c in info["competitions"]
        }
    except Exception:  # noqa: BLE001  (no DB on this machine: the page still shows the logs)
        return "unavailable", {}


def page(runs_dir: Path | None = None):
    st.title("Data health")
    runs, sample = load_runs(Path(runs_dir) if runs_dir is not None else RUNS_DIR), False
    if not runs and runs_dir is None:
        runs, sample = load_runs(SAMPLE_DIR), True
    if sample:
        st.info(
            "SAMPLE DATA: nothing recorded yet in data/runs/. The runs below are examples. "
            "Click 'Run health check' to record a real one."
        )
    _actions()

    stamp, latest = _db_cards()
    a, b, c = st.columns(3)
    with a, st.container(border=True):
        st.markdown("**Last run**")
        st.markdown(
            f"### {ICON[_status(runs[0])] + ' ' + runs[0]['run_id'] if runs else 'no runs'}"
        )
    with b, st.container(border=True):
        st.markdown("**Database updated**")
        st.markdown(f"### {stamp}")
    with c, st.container(border=True):
        st.markdown("**Runs recorded**")
        st.markdown(f"### {len(runs)}")
    if latest:
        st.caption(
            "Latest match per competition: " + ", ".join(f"{k} {v}" for k, v in latest.items())
        )

    if not runs:
        st.caption("No run logs yet.")
        return
    st.subheader("Runs (newest first)")
    st.dataframe(
        pd.DataFrame([_summary_row(r) for r in runs]).astype(str), hide_index=True, width="stretch"
    )
    ids = [r["run_id"] for r in runs]
    _detail(runs[ids.index(st.selectbox("Open a run", ids, key="health_run"))])
