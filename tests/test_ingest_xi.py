from cricket_analytics.ingest import xi

INFO = "version,2.3.0\ninfo,gender,female\ninfo,team,A\ninfo,team,B\n" + "".join(
    f"info,player,{t},{t}{i}\n" for t in "AB" for i in range(11)
) + "info,registry,people,A0,abc\n"


def test_build_and_coverage(tmp_path):
    d = tmp_path / "t20s"
    d.mkdir()
    (d / "123_info.csv").write_text(INFO)
    df = xi.build(raw_root=tmp_path, write=False)
    assert len(df) == 22 and set(df.n_listed) == {11} and set(df.competition) == {"t20i_women"}
    assert df.match_id.iloc[0] == "123" and xi.coverage(df).loc["t20i_women", 11] == 2


def test_xi_from_info(tmp_path):
    import pandas as pd

    from cricket_analytics.ml import resources as R

    (tmp_path / "t20s").mkdir()
    (tmp_path / "t20s" / "123_info.csv").write_text(INFO)
    p = tmp_path / "xi.parquet"
    xi.build(raw_root=tmp_path, write=False).drop(columns="competition").to_parquet(p)
    d = pd.DataFrame({"match_id": ["123"], "innings": [1], "batting_team": ["A"], "bowling_team": ["B"], "batter": ["A0"],
                      "non_striker": ["A1"], "bowler": ["B3"], "fielder": [None], "fielder_2": [None], "fielder_3": [None]})
    out = R.xi_from_info(d, path=p)
    assert len(out) == 22 and out.set_index(["team", "player"]).loc[("A", "A0"), "batted"] and not out.batted.iloc[-1]


def test_fresh3_mask():
    import pandas as pd
    import pytest

    from cricket_analytics.ml import evaluate as E

    df = pd.DataFrame({"gender": ["male"] * 5 + ["female"], "competition": ["t20i", "t20i", "bbl", "bbl", "t20i", "t20i"],
                       "date": ["2026-10-20", "2026-10-20", "2026-10-20", "2026-10-14", "2026-10-20", "2026-10-20"],
                       "batting_team": ["India", "India", "X", "X", "India", "India"], "bowling_team": ["Australia", "Nepal", "Y", "Y", "Australia", "Australia"]})
    assert E.fresh3_mask(df).tolist() == [True, False, True, False, True, False][:4] + [True, False]
    with pytest.raises(ValueError):
        E.assert_no_fresh3(df, "train")
    E.assert_no_fresh3(df.iloc[[1, 3, 5]], "train")
