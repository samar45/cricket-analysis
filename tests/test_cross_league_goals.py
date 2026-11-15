"""Goal tests for the cross-league player profile (state leagues + SMAT 2025 + IPL/T20I). Frozen.

Golden facts were checked by hand from the Cricbuzz scorecards. SMAT 2026 and DB matches dated 2026-10-15 or later are out.
"""
import pandas as pd
import pytest

from cricket_analytics.db import query
from cricket_analytics.scouting import profile as P

pytestmark = pytest.mark.skipif(not P.available(), reason="local Cricbuzz data not present")


def _runs(df, comp, season=None):
    d = df[df.competition.str.contains(comp, regex=False)]
    if season:
        d = d[d.season.astype(str) == str(season)]
    return int(d.runs.sum())


def test_naman_dhir_sher_e_punjab_2026():
    assert _runs(P.profile("36139"), "Sher-e-Punjab", 2026) == 655


def test_karun_nair_maharaja_all_seasons():
    assert _runs(P.profile("Karun Nair"), "Maharaja") == 1429


def test_ishan_kishan_smat_2025():
    assert _runs(P.profile("Ishan Kishan"), "SMAT", "2025") == 517


def test_kushagra_two_spellings_one_player():
    assert _runs(P.profile("15779"), "SMAT", "2025") == 422


def test_naman_dhir_ipl_equals_direct_db_query():
    got = P.profile("36139")
    ipl = got[got.competition == "IPL"]
    assert len(ipl) >= 1 and (ipl.link == "team_checked").all()
    direct = query("SELECT sum(runs_batter) r FROM deliveries d JOIN matches m USING (match_id) "
                   "WHERE m.competition='ipl' AND m.gender='male' AND d.batter='Naman Dhir' AND d.innings<=2 "
                   "AND m.date < DATE '2026-10-15'").r[0]
    assert int(ipl.runs.sum()) == int(direct)


def test_sahaj_dhawan_not_merged_with_shikhar():
    got = P.profile("Sahaj Dhawan")
    assert len(got) > 0  # his own state-league rows are there
    cs = got[~got.source.str.startswith("cricbuzz")]
    assert cs.empty or (cs.link == "doubtful").all()
    assert not ((got.competition == "IPL") & (got.link != "doubtful")).any()


def test_every_row_has_source_and_link_and_no_2026_10_15_plus():
    for q in ("36139", "Karun Nair", "Ishan Kishan"):
        got = P.profile(q)
        assert got.source.notna().all() and got.link.isin(["strong", "team_checked", "name_only", "doubtful"]).all()
        assert (pd.to_datetime(got.last_date) < pd.Timestamp("2026-10-15")).all()


def test_ambiguous_name_raises_with_candidates():
    with pytest.raises(ValueError, match="candidates|ambiguous"):
        P.profile("Rishabh Sharma")


def test_board_columns_and_unique_ids():
    b = P.board(min_balls=100)
    assert "ipl_capped" in b.columns and len(b) > 50
    assert not b.cricbuzz_id.duplicated().any()
    assert set(b.ipl_capped) <= {"yes", "no", "unknown"}
    assert b.loc[b.cricbuzz_id == 36139, "ipl_capped"].iloc[0] == "yes"
