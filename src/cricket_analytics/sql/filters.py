"""Filters -> (WHERE sql, bind params). Every value is bound with `?`; nothing is interpolated."""

from dataclasses import dataclass
from typing import Literal

from .. import competitions
from .fragments import PHASES, phase_sql

Side = Literal["bat", "bowl", "match"]


def _in(col: str, vals: list) -> tuple[str, list]:
    """`col = ?` for one value, `col IN (?, ?)` for several, ('', []) for none. Values are always bound."""
    if not vals:
        return "", []
    return (f"{col} = ?", list(vals)) if len(vals) == 1 else (f"{col} IN ({', '.join('?' * len(vals))})", list(vals))


@dataclass
class Filters:
    """What to look at. All fields optional; `None` = no restriction.

    competition: key from competitions.py. None = all competitions, MEN'S ONLY (women's data is
                 reached only with competition='t20i_women').
    season:      one value or a list of them (empty list = no filter). Each is a Cricsheet label
                 ('2007/08', '2024') or a year (2008 / '2008'). A year matches seasons whose first match
                 falls in that year for that competition, so IPL 2008 = '2007/08' and IPL 2020 = '2020/21'.
                 A 4-digit value also matches an identical label.
    season_from, season_to: inclusive years, mapped like `season` (a season's year = year of its first match).
                 season_from=2022 keeps IPL 2022, 2023, ...; BBL '2021/22' counts as 2021.
    last_n_years: the N most recent SEASONS of each competition in scope (by first match date), not calendar
                 years: leagues play once a year, so for them N seasons = N years. For T20Is, where Cricsheet
                 splits a year into labels such as '2024' and '2024/25', N seasons is fewer than N years.
                 "Most recent" is relative to the data, so after the 2026 IPL, N=5 is 2022..2026.
                 season, season_from/to and last_n_years combine with AND.
    team, opposition, venue: one exact name or a list (a match on any of them); never LIKE. Names may contain
                 commas, so pass lists, not comma-joined strings.
    player:      exact match, single. Use api.resolve_player() first.
    phase:       powerplay | middle | death (ignored for side='match').
    include_super_overs: False (default) drops super-over innings (innings 3+ in these limited-overs
                 matches; measured: every innings > 2 belongs to a tied match, 74 matches), as official
                 records do. For side='bat'/'bowl' the condition is inside .where(); modules that read
                 deliveries with side='match' add `f.innings_sql()` themselves.
    """
    competition: str | None = None
    season: str | int | list | tuple | None = None
    team: str | list | tuple | None = None
    opposition: str | list | tuple | None = None
    venue: str | list | tuple | None = None
    season_from: int | None = None
    season_to: int | None = None
    last_n_years: int | None = None
    phase: str | None = None
    player: str | None = None
    include_super_overs: bool = False

    def values(self, name: str) -> list:
        """The filter `name` as a list of non-empty values ([] = no filter), whether it was set as one value or many."""
        v = getattr(self, name)
        if v is None:
            return []
        return [x for x in (v if isinstance(v, (list, tuple, set)) else [v]) if x is not None and str(x).strip() != ""]

    def _season_sql(self, m: str) -> tuple[str, list]:
        """One condition on m.season / m.competition, or ('', [])."""
        items = [str(x).strip() for x in self.values("season")]
        lo, hi, n = self.season_from, self.season_to, self.last_n_years
        if lo is not None and hi is not None and int(lo) > int(hi):
            raise ValueError(f"season_from ({lo}) must not be after season_to ({hi})")
        if n is not None and int(n) < 1:
            raise ValueError(f"last_n_years must be 1 or more, got {n}")
        years = [int(x) for x in items if len(x) == 4 and x.isdigit()]
        if items and not (years or lo is not None or hi is not None or n is not None):
            return _in(f"{m}.season", items)   # plain labels: no need to look at match dates
        if not (items or lo is not None or hi is not None or n is not None):
            return "", []
        # one row per season of the scoped competition(s): its year (first match) and its rank, newest first
        scope, sp = ("gender = ?", [competitions.DEFAULT_GENDER]) if self.competition is None else             ("competition = ? AND gender = ?", [competitions.get(self.competition).competition,
                                                competitions.get(self.competition).gender])
        conds: list[str] = []
        p: list = []
        if items:
            lab, lp = _in("season", items)
            conds.append(lab if not years else f"({lab} OR y IN ({', '.join('?' * len(years))}))")
            p += lp + years
        if lo is not None:
            conds.append("y >= ?")
            p.append(int(lo))
        if hi is not None:
            conds.append("y <= ?")
            p.append(int(hi))
        if n is not None:
            conds.append("rn <= ?")
            p.append(int(n))
        sub = (f"SELECT competition, season, year(min(date)) AS y, "
               f"row_number() OVER (PARTITION BY competition ORDER BY min(date) DESC) AS rn "
               f"FROM matches WHERE {scope} GROUP BY competition, season")
        return (f"({m}.competition, {m}.season) IN (SELECT competition, season FROM ({sub}) WHERE {' AND '.join(conds)})",
                sp + p)

    def innings_sql(self, d: str = "d") -> str:
        """'d.innings <= 2' unless super overs are included; always a valid boolean expression."""
        return "1=1" if self.include_super_overs else f"{d}.innings <= 2"

    def where(self, side: Side, d: str = "d", m: str = "m") -> tuple[str, list]:
        """Build the WHERE body (always starts with `1=1`).

        side='bat'   : `team` is the batting side, `opposition` the bowling side, `player` the batter.
        side='bowl'  : `team` is the bowling side, `opposition` the batting side, `player` the bowler.
        side='match' : `team`/`opposition` are either of team1/team2; player and phase are ignored.
        Needs `deliveries` aliased as `d` (not for 'match') and `matches` aliased as `m`.
        """
        if side not in ("bat", "bowl", "match"):
            raise ValueError(f"side must be bat, bowl or match, not {side!r}")
        c: list[str] = ["1=1"]
        p: list = []

        if self.competition is None:
            c.append(f"{m}.gender = ?")
            p.append(competitions.DEFAULT_GENDER)
        else:
            comp = competitions.get(self.competition)
            c.append(f"{m}.competition = ? AND {m}.gender = ?")
            p += [comp.competition, comp.gender]

        sc, sp = self._season_sql(m)
        if sc:
            c.append(sc)
            p += sp

        sc, sp = _in(f"{m}.venue", self.values("venue"))
        if sc:
            c.append(sc)
            p += sp

        if side == "match":
            for name in ("team", "opposition"):
                t = self.values(name)
                if t:
                    (a, ap), (b, bp) = _in(f"{m}.team1", t), _in(f"{m}.team2", t)
                    c.append(f"({a} OR {b})")
                    p += ap + bp
            return " AND ".join(c), p

        if not self.include_super_overs:
            c.append(self.innings_sql(d))
        mine, other, who = (("batting_team", "bowling_team", "batter") if side == "bat"
                            else ("bowling_team", "batting_team", "bowler"))
        for col, name in ((mine, "team"), (other, "opposition")):
            sc, sp = _in(f"{d}.{col}", self.values(name))
            if sc:
                c.append(sc)
                p += sp
        if self.player:
            c.append(f"{d}.{who} = ?")
            p.append(self.player)
        if self.phase:
            if self.phase not in PHASES:
                raise ValueError(f"phase must be one of {PHASES}, not {self.phase!r}")
            c.append(f"{phase_sql(d, m)} = ?")
            p.append(self.phase)
        return " AND ".join(c), p
