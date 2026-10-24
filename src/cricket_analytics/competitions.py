"""User-facing competition keys -> (matches.competition, matches.gender, label).

Women's T20 internationals are their own key (`t20i_women`) because `t20i` is men's only.
Leagues in the DB are men's only today.
"""

from typing import NamedTuple


class Competition(NamedTuple):
    competition: str   # value of matches.competition
    gender: str        # value of matches.gender
    label: str


COMPETITIONS: dict[str, Competition] = {
    "ipl":        Competition("ipl", "male", "IPL"),
    "t20i":       Competition("t20i", "male", "Men's T20 internationals"),
    "t20i_women": Competition("t20i", "female", "Women's T20 internationals"),
    "bbl":        Competition("bbl", "male", "Big Bash League"),
    "psl":        Competition("psl", "male", "Pakistan Super League"),
    "cpl":        Competition("cpl", "male", "Caribbean Premier League"),
    "sa20":       Competition("sa20", "male", "SA20"),
    "hundred":    Competition("hundred", "male", "The Hundred"),
    "blast":      Competition("blast", "male", "T20 Blast"),
}

DEFAULT_GENDER = "male"   # used when no competition is given


def get(key: str) -> Competition:
    try:
        return COMPETITIONS[key]
    except KeyError:
        raise ValueError(f"Unknown competition {key!r}. Choose from: {', '.join(COMPETITIONS)}") from None
