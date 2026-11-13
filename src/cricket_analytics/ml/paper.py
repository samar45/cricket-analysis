"""Paper-trading engine: fake money only. Never places real bets, never talks to any bookmaker or exchange.

Rules (docs/ML_PREDICTION.md section 9, part C): EV = p*(price-1)*0.95 - (1-p); bet only if EV >= 0.03;
stake = quarter Kelly capped at 5% of bankroll; start 5000; one bet per match; "make N" = top N by EV.
Model-agnostic: p_model comes from any column.

  python -m cricket_analytics.ml.paper replay
  python -m cricket_analytics.ml.paper demo --n 2
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PAPER_DIR = ROOT / "data" / "external" / "paper"
COMMISSION, MIN_EV, KELLY_FRAC, CAP, START = 0.05, 0.03, 0.25, 0.05, 5000.0
BANNER = "paper trading, fake money"


def ev(p: float, price: float) -> float:
    """Expected profit per 1 unit staked, with commission on winnings."""
    return p * (price - 1) * (1 - COMMISSION) - (1 - p)


def stake_for(p: float, price: float, bankroll: float) -> float:
    """Quarter Kelly (commission-adjusted odds), capped at 5% of bankroll, never negative."""
    b = (price - 1) * (1 - COMMISSION)
    if b <= 0 or bankroll <= 0:
        return 0.0
    return float(max(0.0, min(KELLY_FRAC * ev(p, price) / b, CAP)) * bankroll)


@dataclass
class Opportunity:
    match: str
    checkpoint: int
    side: str
    p_model: float
    price: float
    ev: float
    date: pd.Timestamp | None = None


@dataclass
class Bet:
    match: str
    checkpoint: int
    side: str
    p_model: float
    price: float
    ev: float
    stake: float
    date: pd.Timestamp | None = None
    status: str = "open"  # open | won | lost
    pnl: float = 0.0


class Ledger:
    def __init__(self, bankroll: float = START, path: Path | str | None = PAPER_DIR / "ledger.jsonl"):
        self.start = self.bankroll = float(bankroll)  # bankroll = cash; open stakes are held out of it
        self.bets: list[Bet] = []
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def has_bet(self, match: str) -> bool:
        return any(b.match == match for b in self.bets)

    def log(self, **rec):
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")


def _skip(led: Ledger, o: Opportunity, reason: str):
    led.log(decision="skip", reason=reason, match=o.match, checkpoint=o.checkpoint, side=o.side, p_model=o.p_model,
            price=o.price, ev=o.ev, bankroll=led.bankroll)


def make_bets(opps: list[Opportunity], n: int | None, led: Ledger) -> tuple[list[Bet], str]:
    """Place the top n (None = all) qualifying opportunities by EV, at most one per match. Returns (bets, explanation)."""
    bank = led.bankroll  # all stakes in this call are sized on the bankroll at the start of the call
    qualifying = []
    for o in opps:
        if o.ev < MIN_EV:
            _skip(led, o, f"EV {o.ev:.3f} below {MIN_EV}")
        elif led.has_bet(o.match):
            _skip(led, o, "match already has a bet")
        else:
            qualifying.append(o)
    qualifying.sort(key=lambda o: -o.ev)
    placed, seen = [], set()
    for o in qualifying:
        if o.match in seen:
            _skip(led, o, "a better opportunity on the same match was taken")
        elif n is not None and len(placed) >= n:
            _skip(led, o, f"qualifies but outside the top {n}")
        elif (s := stake_for(o.p_model, o.price, bank)) <= 0:
            _skip(led, o, "stake is zero")
        else:
            b = Bet(o.match, o.checkpoint, o.side, o.p_model, o.price, o.ev, s, o.date)
            led.bankroll -= s
            led.bets.append(b)
            placed.append(b)
            seen.add(o.match)
            led.log(decision="bet", reason=f"EV {o.ev:.3f} >= {MIN_EV}, rank {len(placed)}", match=o.match, checkpoint=o.checkpoint,
                    side=o.side, p_model=o.p_model, price=o.price, ev=o.ev, stake=s, bankroll_before=bank, bankroll_after=led.bankroll)
    k = "all" if n is None else n
    low = sum(o.ev < MIN_EV for o in opps)
    if n is not None and len(placed) == n:
        why = f"placed {n} of {n}: top {n} by EV among {len(qualifying)} with EV >= {MIN_EV:.0%}"
    else:
        why = f"placed {len(placed)} of {k}: only {len(qualifying)} of {len(opps)} opportunities have EV >= {MIN_EV:.0%}"
    if low:
        why += f" ({low} below the threshold)"
    return placed, why + f" [{BANNER}]"


def settle(bet: Bet, side_won: bool, led: Ledger) -> Bet:
    """Win returns stake plus winnings minus commission; loss returns nothing."""
    assert bet.status == "open", "bet already settled"
    bet.pnl, bet.status = (bet.stake * (bet.price - 1) * (1 - COMMISSION), "won") if side_won else (-bet.stake, "lost")
    led.bankroll += bet.stake + bet.pnl
    led.log(decision="settle", match=bet.match, side=bet.side, status=bet.status, pnl=bet.pnl, bankroll=led.bankroll)
    return bet


def opportunities(rows: pd.DataFrame, p_col: str) -> list[Opportunity]:
    """Both sides of each row (chaser at p, opponent at 1-p), skipping sides with no valid price."""
    out = []
    for r in rows.to_dict("records"):
        p = float(r[p_col])
        for side, q, pr in ((r["chaser"], p, r["price_chaser"]), (r["opponent"], 1 - p, r["price_opp"])):
            if pr == pr and pr > 1:
                out.append(Opportunity(str(r["match_id"]), int(r["balls_bowled"]), side, q, float(pr), ev(q, float(pr)), r["date"]))
    return out


def replay(rows: pd.DataFrame, p_col: str = "p_ens-G1", bankroll: float = START, log_path: Path | str | None = None,
           n_boot: int = 2000, seed: int = 0) -> dict:
    """Walk forward by date. Rows: match_id, date, balls_bowled, chaser, opponent, price_chaser, price_opp, y (chaser won), p_col.
    A day's bets (first qualifying checkpoint per match) are all placed before any of that day's results are read."""
    led = Ledger(bankroll, log_path)
    curve = [led.bankroll]
    rows = rows.sort_values(["date", "match_id", "balls_bowled"], kind="stable")
    for _, day in rows.groupby("date", sort=True):
        pending = []
        for _, m in day.groupby("match_id", sort=False):
            for _, r in m.iterrows():  # checkpoints in time order; stop at the first that qualifies
                os_ = opportunities(r.to_frame().T, p_col)
                if any(o.ev >= MIN_EV for o in os_):
                    placed, _ = make_bets(os_, None, led)
                    pending += [(b, r.y, r.chaser) for b in placed]
                    break
        for b, y, chaser in pending:  # results are read only now
            settle(b, (float(y) == 1.0) == (b.side == chaser), led)
        curve.append(led.bankroll)
    bets = led.bets
    staked = sum(b.stake for b in bets)
    c = np.asarray(curve)
    out = dict(final_bankroll=led.bankroll, n_bets=len(bets), bets=bets, ledger=led, curve=curve,
               hit_rate=float(np.mean([b.status == "won" for b in bets])) if bets else float("nan"),
               roi=sum(b.pnl for b in bets) / staked if staked else float("nan"),
               max_drawdown=float(np.max(1 - c / np.maximum.accumulate(c))), roi_ci=(float("nan"), float("nan")))
    if bets:
        pnl, st = np.array([b.pnl for b in bets]), np.array([b.stake for b in bets])
        idx = np.random.default_rng(seed).integers(0, len(bets), (n_boot, len(bets)))
        r = pnl[idx].sum(1) / st[idx].sum(1)
        out["roi_ci"] = (float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5)))
    return out


def load_replay_rows() -> pd.DataFrame:
    """Betfair BBL benchmark rows plus the lower of back/lay price per runner at each checkpoint."""
    from . import market as mk

    rows = pd.read_parquet(mk.ML_DIR / "market_rows.parquet")
    odds = mk.load_odds()
    odds["RUNNER_NAME"] = odds.RUNNER_NAME.map(mk._canon)
    parts = []
    for b, snap in mk.SNAP.items():
        two = odds[[f"BEST_BACK_{snap}", f"BEST_LAY_{snap}"]].astype(float).where(lambda x: x > 1.0)
        parts.append(pd.DataFrame({"EVENT_ID": odds.EVENT_ID, "RUNNER_NAME": odds.RUNNER_NAME, "price": two.min(axis=1), "balls_bowled": float(b)}))
    px = pd.concat(parts).dropna(subset=["price"])
    rows = rows.assign(balls_bowled=rows.balls_bowled.astype(float))
    rows = rows.merge(px.rename(columns={"RUNNER_NAME": "chaser", "price": "price_chaser"}), on=["EVENT_ID", "chaser", "balls_bowled"], how="left")
    opp = px.rename(columns={"RUNNER_NAME": "opponent", "price": "price_opp"})
    rows = rows.merge(opp, on=["EVENT_ID", "balls_bowled"], how="left")
    rows = rows[rows.opponent != rows.chaser]
    return rows.drop_duplicates(["match_id", "balls_bowled"]).reset_index(drop=True)


def _print_summary(s: dict):
    lo, hi = s["roi_ci"]
    print(f"final bankroll {s['final_bankroll']:.2f} (start {s['ledger'].start:.0f}), bets {s['n_bets']}, hit rate {s['hit_rate']:.3f}, "
          f"ROI {s['roi']:+.3%} (bootstrap 95% {lo:+.3%} to {hi:+.3%}), max drawdown {s['max_drawdown']:.1%}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=BANNER)
    ap.add_argument("cmd", choices=["replay", "demo"])
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--p-col", default="p_ens-G1")
    a = ap.parse_args(argv)
    print(BANNER)
    rows = load_replay_rows()
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    if a.cmd == "replay":
        f = PAPER_DIR / "replay_ledger.jsonl"
        f.write_text("", encoding="utf-8")
        _print_summary(replay(rows, a.p_col, log_path=f))
        return
    opps = opportunities(rows, a.p_col)
    d0 = pd.Series([o.date for o in opps if o.ev >= MIN_EV]).value_counts().idxmax()  # busiest day with qualifying opportunities
    opps = [o for o in opps if o.date == d0]
    placed, why = make_bets(opps, a.n, Ledger(path=PAPER_DIR / "ledger.jsonl"))
    print(f"day {d0.date()}: {len(opps)} opportunities\n{why}")
    for b in placed:
        print(f"  match {b.match} at {b.checkpoint // 6} overs: back {b.side}, p={b.p_model:.3f}, price {b.price:.2f}, EV {b.ev:.3f}, stake {b.stake:.2f}")


if __name__ == "__main__":
    main()
