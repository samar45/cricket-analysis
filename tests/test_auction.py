"""Auction price model and market check (models/auction.py, module `auction`). Most tests read the saved files only."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cricket_analytics import api
from cricket_analytics.models import auction as A
from cricket_analytics.viz import auction as aviz
from cricket_analytics.viz import video
from tests.conftest import requires_real_db


def test_prior_contract_uses_only_earlier_deals():
    ev = pd.DataFrame(
        {
            "pid": ["x", "x", "x"],
            "order": [2022.0, 2024.5, 2025.0],
            "year": [2022, 2025, 2025],
            "price": [1.0, 5.0, 9.0],
            "retained": [0, 1, 0],
        }
    )
    assert A.prior_contract("x", 2022, ev) is None  # same-year auction is not "before"
    assert A.prior_contract("x", 2024, ev)[0] == 1.0
    assert A.prior_contract("x", 2025, ev) == (
        5.0,
        2025,
        1,
    )  # a retention in cycle 2025 precedes the 2025 auction
    assert A.prior_contract("x", 2026, ev)[0] == 9.0


def test_saved_features_have_no_leakage():
    f = pd.read_csv(A.FEATURES)
    p = f.dropna(subset=["prior_year"])
    assert (p.prior_year <= p.auction_year).all()
    same = p[p.prior_year == p.auction_year]
    assert (same.prior_ret == 1).all()  # same-year prior deal can only be that cycle's retention
    assert f.groupby("auction_year").prior_price.apply(lambda s: s.notna().sum()).loc[2022] == 0
    assert (f.ipl_balls <= f.t20_balls + 1e-9).all()
    assert set(f.auction_year) == set(A.YEARS)


def test_predictions_are_valid():
    d = pd.read_csv(A.PREDS)
    assert d.p_sold.between(0, 1).all()
    assert (d.p10 <= d.p50 + 1e-9).all() and (d.p50 <= d.p90 + 1e-9).all()
    assert (d.p10 >= d.base_price_cr - 1e-9).all()  # nobody sells below base
    kinds = d.groupby("auction_year").pred_kind.first().to_dict()
    assert kinds == {2022: "oof", 2023: "oof", 2024: "oof", 2025: "validation", 2026: "test"}
    s = d[d.sold]
    assert (s.price_cr >= s.base_price_cr - 1e-9).all()


def test_saved_model_block():
    m = A.load_model()
    fm = m["final_model"]
    assert fm["train_years"] == [2022, 2023, 2024, 2025]
    assert fm["quantiles_log"]["p10"] < fm["quantiles_log"]["p50"] < fm["quantiles_log"]["p90"]
    assert len(fm["price"]["cols"]) == len(fm["price"]["beta"]) == len(fm["price"]["m"])
    assert 0.5 < m["test"]["model"]["cover_80"] <= 1.0
    assert m["target"] in ("A", "B") and m["group"] in A.GROUPS


def test_ridge_and_logistic_recover_signal():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 3))
    y = 2 * X[:, 0] - X[:, 1] + rng.normal(scale=0.1, size=2000)
    M = A.ridge_fit(X, y, 1.0)
    assert np.abs(A.lin_predict(M, X) - y).mean() < 0.2
    yb = (X[:, 0] + rng.normal(size=2000) > 0).astype(float)
    L = A.logit_fit(X, yb, 1.0)
    p = A.logit_predict(L, X)
    assert ((p >= 0) & (p <= 1)).all() and A.auc(yb, p) > 0.75


def test_auc_and_spearman_known_values():
    assert A.auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert A.auc(np.array([0, 1, 0, 1]), np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert A.spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)


def test_market_table_and_bootstrap():
    b = A.load_market()
    assert set(b.type) == {"overseas", "capped Indian", "uncapped Indian"}
    t = A.market_table(b, "type")
    assert (t.lo <= t.war_per_10cr).all() and (t.war_per_10cr <= t.hi).all()
    assert t.players.sum() == len(b[b.year.isin((2022, 2023, 2024, 2025))])
    est, lo, hi = A.bootstrap_ratio(np.array([1.0, 0.0, 2.0, -1.0]), np.array([1.0, 1.0, 2.0, 2.0]))
    assert lo <= est <= hi and est == pytest.approx(2 / 6 * 10)


def test_train_val_test_split_is_fixed():
    assert A.TRAIN == (2022, 2023, 2024) and A.VAL == 2025 and A.TEST == 2026


@requires_real_db
def test_module_views_and_charts():
    r = api.run("auction")
    assert len(r.data) > 0 and {"p10_cr", "p50_cr", "p90_cr", "p_sold"} <= set(r.data.columns)
    assert aviz.figure(r) is not None and "auction" in video.module_ids()
    m = api.run("auction", view="market", group_by="type")
    assert len(m.data) == 3 and aviz.figure(m) is not None
    p = api.run("auction", view="player", player="Cameron Green")
    assert (p.data.auction >= 2023).all() and len(p.data) >= 1
    with pytest.raises(ValueError):
        api.run("auction", view="player")
    with pytest.raises(ValueError):
        api.run("auction", competition="bbl")


@requires_real_db
def test_auction_room_page_renders_every_section():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        str(Path(__file__).parent.parent / "dashboard" / "app.py"), default_timeout=180
    ).run()
    at.sidebar.radio(key="page").set_value("Auction room").run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error and not [w for w in at.warning if "Check your filters" in w.value]
    heads = [s.value for s in at.subheader]
    for h in ("2027 needs", "Scarce roles", "Price estimator", "Uncapped scouting", "Market check"):
        assert h in heads
    assert len(at.dataframe) >= 9  # needs, scarcity, estimator, 2 scouting lists, 3 market tables
    assert any("PROVISIONAL" in w.value for w in at.warning)
    assert any("did NOT raise prices" in i.value for i in at.info)
    assert any("barely beats" in c.value for c in at.caption)
    at.selectbox(key="ar_player").set_value("Prabhsimran Singh").run()
    assert not at.exception


def test_wrong_initials_matches_are_blank_and_right_ones_kept():
    a = A.fix_names(pd.read_csv(A.REF / "ipl_auctions.csv"))
    nm = a.groupby("player").cricsheet_name.first()
    for wrong in (
        "Sonu Yadav",
        "Mangesh Yadav",
        "Upendra Yadav",
        "Gaurav Gambhir",
        "Mohammed Kaif",
    ):
        assert pd.isna(nm[wrong]), wrong
    assert nm["Mayank Yadav"] == "MP Yadav" and nm["Prabhsimran Singh"] == "P Simran Singh"
    assert nm["Umesh Yadav"] == "UT Yadav"


def test_cheapest_table_and_played_share():
    mk = A.load_market()
    c = A.cheapest_table(mk)
    assert set(c.group) == {"capped Indian", "overseas", "retained", "uncapped Indian"}
    # the cheapest-alternative rate is a cycle mean, so it shifts every group by a small amount only
    assert (c.war_per_10cr_vs_cheapest - c.war_per_10cr_vs_average).abs().max() < 0.3
    cheap = mk[(mk.source == "auction") & (mk.base <= A.CHEAP_BASE) & (mk.price <= mk.base + 1e-9)]
    assert abs((cheap.war - cheap.cheap_war).groupby(cheap.year).sum()).max() < 1e-6
    assert len(A.played_share(mk)) == 4
