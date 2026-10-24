"""The one place that defines competitions: user-facing key, label, gender, and where the data comes from.

Women's T20 internationals are their own key (`t20i_women`) because `t20i` is men's only. Both live in the same
Cricsheet zip / raw folder (`t20s`). Leagues in the DB are men's only today.
"""

from typing import NamedTuple


class Competition(NamedTuple):
    competition: str        # value of matches.competition
    gender: str             # value of matches.gender
    label: str
    folder: str             # Cricsheet key = sub-folder under data/raw/cricsheet/ and the `formats` names in config.yaml
    url: str                # Cricsheet CSV2 zip
    format_label: str       # legacy matches.format value (IPL stays "T20"; use competition + gender instead)
    tournament_label: str   # matches.tournament fallback when a match has no event name


_DL = "https://cricsheet.org/downloads/"

COMPETITIONS: dict[str, Competition] = {
    "ipl":        Competition("ipl", "male", "IPL", "ipl", _DL + "ipl_csv2.zip", "T20", "IPL"),
    "t20i":       Competition("t20i", "male", "Men's T20 internationals", "t20s", _DL + "t20s_csv2.zip", "T20", "T20I"),
    "t20i_women": Competition("t20i", "female", "Women's T20 internationals", "t20s", _DL + "t20s_csv2.zip", "T20", "T20I"),
    "bbl":        Competition("bbl", "male", "Big Bash League", "bbl", _DL + "bbl_csv2.zip", "BBL", "Big Bash League"),
    "psl":        Competition("psl", "male", "Pakistan Super League", "psl", _DL + "psl_csv2.zip", "PSL", "Pakistan Super League"),
    "cpl":        Competition("cpl", "male", "Caribbean Premier League", "cpl", _DL + "cpl_csv2.zip", "CPL", "Caribbean Premier League"),
    "sa20":       Competition("sa20", "male", "SA20", "sa20", _DL + "sat_male_csv2.zip", "SA20", "SA20"),
    "hundred":    Competition("hundred", "male", "The Hundred", "hundred", _DL + "hnd_male_csv2.zip", "Hundred", "The Hundred"),
    "blast":      Competition("blast", "male", "T20 Blast", "blast", _DL + "ntb_male_csv2.zip", "Blast", "Vitality T20 Blast"),
}

# Cricsheet folder key -> its Competition (what the loader uses). The t20s folder holds men and women; the entry
# is the men's one, the loader reads the gender from each match.
BY_FOLDER: dict[str, Competition] = {}
for _c in COMPETITIONS.values():
    BY_FOLDER.setdefault(_c.folder, _c)

DEFAULT_GENDER = "male"   # used when no competition is given


def get(key: str) -> Competition:
    try:
        return COMPETITIONS[key]
    except KeyError:
        raise ValueError(f"Unknown competition {key!r}. Choose from: {', '.join(COMPETITIONS)}") from None
