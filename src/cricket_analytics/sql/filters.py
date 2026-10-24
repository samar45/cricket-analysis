"""Filters -> (WHERE sql, bind params). Every value is bound with `?`; nothing is interpolated."""

from dataclasses import dataclass
from typing import Literal

from .. import competitions
from .fragments import PHASES, phase_sql

Side = Literal["bat", "bowl", "match"]


@dataclass
class Filters:
    """What to look at. All fields optional; `None` = no restriction.

    competition: key from competitions.py. None = all competitions, MEN'S ONLY (women's data is
                 reached only with competition='t20i_women').
    season:      a Cricsheet label ('2007/08', '2024') or a year (2008 / '2008'). A year matches
                 seasons whose first match falls in that year for that competition, so
                 IPL 2008 = '2007/08' and IPL 2020 = '2020/21'. A 4-digit value also matches an
                 identical label.
    team, opposition, venue, player: exact match (never LIKE). Use api.resolve_player() first.
    phase:       powerplay | middle | death (ignored for side='match').
    """
    competition: str | None = None
    season: str | int | None = None
    team: str | None = None
    opposition: str | None = None
    venue: str | None = None
    phase: str | None = None
    player: str | None = None

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

        if self.season is not None and str(self.season) != "":
            s = str(self.season).strip()
            if len(s) == 4 and s.isdigit():
                c.append(f"({m}.season = ? OR ({m}.competition, {m}.season) IN "
                         "(SELECT competition, season FROM matches GROUP BY ALL HAVING year(min(date)) = ?))")
                p += [s, int(s)]
            else:
                c.append(f"{m}.season = ?")
                p.append(s)

        if self.venue:
            c.append(f"{m}.venue = ?")
            p.append(self.venue)

        if side == "match":
            for t in (self.team, self.opposition):
                if t:
                    c.append(f"({m}.team1 = ? OR {m}.team2 = ?)")
                    p += [t, t]
            return " AND ".join(c), p

        mine, other, who = (("batting_team", "bowling_team", "batter") if side == "bat"
                            else ("bowling_team", "batting_team", "bowler"))
        if self.team:
            c.append(f"{d}.{mine} = ?")
            p.append(self.team)
        if self.opposition:
            c.append(f"{d}.{other} = ?")
            p.append(self.opposition)
        if self.player:
            c.append(f"{d}.{who} = ?")
            p.append(self.player)
        if self.phase:
            if self.phase not in PHASES:
                raise ValueError(f"phase must be one of {PHASES}, not {self.phase!r}")
            c.append(f"{phase_sql(d, m)} = ?")
            p.append(self.phase)
        return " AND ".join(c), p
