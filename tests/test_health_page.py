"""Data health page with AppTest, on the sample logs, an empty dir and a corrupt dir. No DB needed."""

import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

FIX = Path(__file__).parent / "fixtures" / "runs"


def _script(d):
    import sys
    sys.path.insert(0, d[1])
    import health
    health.page(d[0])


def open_page(runs_dir: Path) -> AppTest:
    root = str(Path(__file__).parent.parent / "dashboard")
    return AppTest.from_function(_script, args=((str(runs_dir), root),), default_timeout=60).run()


def test_each_sample_run_opens():
    at = open_page(FIX)
    assert not at.exception
    ids = sorted(p.stem for p in FIX.glob("*.json"))
    assert len(ids) == 3
    for rid in ids:
        at = at.selectbox(key="health_run").set_value(rid).run()
        assert not at.exception, rid
    at = at.selectbox(key="health_run").set_value("20261025-090000").run()
    assert "check failed: old_data_unchanged" in " ".join(e.value for e in at.error)


def test_empty_dir(tmp_path):
    at = open_page(tmp_path)
    assert not at.exception
    assert any("No run logs" in c.value for c in at.caption)


def test_corrupt_files(tmp_path):
    shutil.copy(next(FIX.glob("*.json")), tmp_path / "20260101-000000.json")
    (tmp_path / "20260102-000000.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "20260103-000000.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / "20260104-000000.json").write_text('{"checks": "oops", "steps": [1], "freshness_after": 5}', encoding="utf-8")
    at = open_page(tmp_path)
    assert not at.exception
    ids = list(at.selectbox(key="health_run").options)
    assert len(ids) == 4
    for rid in ids:
        at = at.selectbox(key="health_run").set_value(rid).run()
        assert not at.exception, rid
