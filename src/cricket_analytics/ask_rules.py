"""Plain-Python rules around the model in ask.py: what is out of scope, which competition the words name, and which
module a strong phrase demands. The model only picks a module; where it clashes with an unmistakable phrase, these win."""

import re

# ---------------------------------------------------------------- out of scope
# (pattern, what the app cannot answer). Checked before the model is called.
_OOS = [
    (
        r"\btests?\s+(?:cricket|match(?:es)?|series|innings|runs|average|wickets|debut|record)\b|\bin\s+tests?\b"
        r"|\bodis?\b|\bone[- ]day\b|\bfirst[- ]class\b|\branji\b|\bcounty championship\b|\bashes\b|\b(?:50|fifty)[- ]over\b"
        r"|\bworld cup final\b.*\b(?:19|20)\d{2}\b.*\bodi\b",
        "Test, ODI or first-class cricket",
    ),
    (
        r"\bline and length\b|\bline\b.*\blength\b|\blengths?\b|\bpitch map\b|\bhawk-?eye\b|\bkm/?h\b|\bkmph\b|\b(?:ball|bowling|delivery) speed\b|\bswing\b",
        "line, length, speed or swing (the data has no ball tracking)",
    ),
    (
        r"\bdropp?(?:ed|s|ing)?\b[^.?]*\bcatch|\bcatch[^.?]*\bdropp?(?:ed|s|ing)?\b|\bmisfields?\b|\bfielding errors?\b",
        "dropped catches or fielding errors (the data does not record them)",
    ),
    (
        r"\bwhich shots?\b|\bwhat shots?\b|\bshot type\b|\bfavou?rite shot\b|\bcover drive\b|\bpull shot\b|\bwagon wheel\b",
        "which shots a batter plays (the data has no shot types)",
    ),
    (
        r"\b(?:weather|rain|raining|forecast|temperature|humidity)\b",
        "weather",
    ),
    (
        r"\b(?:will|who will)\b.*\b(?:win|score|take)\b.*\b(?:tomorrow|next|tonight|upcoming)\b|\bpredict\w*\b.*\b(?:match|final|winner|champions?|tonight)\b|\bwho\b.*\bwin\b.*\btonight\b|\btonight\b|\btomorrow\b",
        "predictions about future matches",
    ),
    (
        r"\b(?:football|soccer|basketball|nba|nfl|tennis|golf|hockey|baseball|formula 1|chess|recipe|bitcoin|stock market|movie|song|capital of)\b",
        "non-cricket topics",
    ),
]


def out_of_scope(question: str) -> str | None:
    """A short reason when the question is about something the T20 ball-by-ball data cannot hold, else None."""
    q = question.lower()
    return next((why for pat, why in _OOS if re.search(pat, q)), None)


# ---------------------------------------------------------------- competition
_COMP = [
    ("t20i_women", r"\bwomen'?s?\b|\bwoman\b|\bfemale\b|\bladies\b|\bwt20i?s?\b"),
    ("ipl", r"\bipl\b|indian premier league"),
    ("t20i", r"\bt20is?\b|\bt20 internationals?\b|\binternationals?\b"),
    ("bbl", r"\bbbl\b|big bash"),
    ("psl", r"\bpsl\b|pakistan super league"),
    ("cpl", r"\bcpl\b|caribbean premier"),
    ("sa20", r"\bsa ?20\b"),
    ("hundred", r"\bthe hundred\b"),
    ("blast", r"\bt20 blast\b|\bvitality\b|\bblast\b"),
]


def competition_in(question: str) -> str | None:
    """The one competition the words name (IPL, T20I, women's, BBL...), else None. Two named -> None (the user must say)."""
    q = question.lower()
    hits = [k for k, pat in _COMP if re.search(pat, q)]
    if "t20i_women" in hits:  # "women's T20Is" names one competition, not two
        hits = [k for k in hits if k != "t20i"]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------- module routing
_KIND = r"spin(?:ners?|ner)?|pace(?:rs?)?|seam(?:ers?)?|fast(?:\s+bowlers?)?|slow(?:\s+bowlers?)?"
# first match wins; the order matters (form beats "last 10 innings"; "get out" beats "against spin")
_ROUTES = [
    # value modules first: their words are unmistakable
    (
        "scarcity",
        r"\bscarc\w*|\bteam needs?\b|\bsupply and demand\b|\bdemand\b.*\b(?:role|keeper|spinner)",
    ),
    (
        "auction",
        r"\bauctions?\b|\bsold for\b|\bwent for\b|\bbought for\b|\bcrores?\b|\bunsold\b|\bprice tag\b|\bmoneyball\b|\bpurse\b",
    ),
    (
        "trade",
        r"\btrad(?:e|es|ed|ing)\b|\bswap(?:s|ped|ping)?\b|\bbest (?:xii|xi|11|12)\b|\bsquad\b",
    ),
    ("wpa", r"\bwin prob\w*|\bwpa\b|\bswung\b|\bswing(?:ed)? (?:the )?(?:game|match)"),
    (
        "war",
        r"\bwar\b|\bwins above replacement\b|\b(?:added|adds|adding) the most wins\b|\bwins added\b|\bprojected\b",
    ),
    (
        "runs_added",
        r"\bruns added\b|\babove (?:the )?average\b|\bruns (?:saved|above)\b|\brun expectancy\b|\bvs (?:the )?average player\b",
    ),
    (
        "matchup_predict",
        r"\bpredict\w*\b|\bper[- ]ball\b|\bek ball\b|\bwhat if\b.*\bfaces?\b|\bhow (?:will|would)\b.*\b(?:do|fare|score)\b.*\b(?:against|vs\.?)\b",
    ),
    (
        "fielding",
        r"\bcatches\b|\bcatchers?\b|\bstumpings?\b|\brun[- ]?outs? (?:effected|involved|by)\b|\bfielders?\b|\bfielding\b|\bbest keepers?\b",
    ),
    ("true_performance", r"\btrue\s+(?:strike|economy|batting|bowling|performance|average)"),
    ("form", r"\bform\b"),
    (
        "dismissal_profile",
        r"\bget(?:s|ting)?\s+(?:\w+\s+){0,2}out\b|\bgot\s+out\b|\bdismiss(?:ed|al|als)\b",
    ),
    (
        "pace_vs_spin",
        rf"\b(?:against|vs\.?|versus)\s+(?:the\s+)?(?:{_KIND})\b|\b(?:{_KIND})\s+(?:vs\.?|versus|and|or)\s+(?:{_KIND})\b",
    ),
    ("home_away", r"\bhome\b|\baway\b"),
    ("chase_vs_set", r"\bdefend(?:ing|s|ed)?\b|\bsetting\b|\bchas(?:e|es|ing|ers?)\b"),
    ("pressure", r"\bpressure\b|\bclutch\b"),
    ("impact", r"\bimpact\b"),
    (
        "innings_list",
        r"\bdebut\b|\b(?:first|last)\s+(?:\d+\s+|\w+\s+)?(?:matches|match|innings|games?)\b|\bbest\s+(?:innings|figures)\b|\bhighest score\b|\btop score\b",
    ),
]
_SPIN_PACE_ALONE = re.compile(rf"\b(?:{_KIND})\b")


def route(
    question: str, current: str | None, has_true: bool | None = None
) -> tuple[str | None, str]:
    """(module, reason) when a strong phrase demands a module different from `current`, else (None, '')."""
    q = question.lower()
    for mod, pat in _ROUTES:
        if re.search(pat, q):
            if mod != current:
                return mod, f"phrase {re.search(pat, q).group(0)!r} means {mod}"
            return None, ""
    if current == "season_awards" and not re.search(
        r"\bseasons?\b|award|debut|\bcap\b|champion|mvp|player of|\b(?:19|20)\d{2}\b", q
    ):  # season_awards is season-by-season; a plain leaderboard is batting / bowling
        return (
            "bowling" if re.search(r"\bbowl|economy|wicket", q) else "batting"
        ), "no season word: a plain leaderboard"
    if current == "true_performance" and not re.search(r"\btrue\b|\badjusted\b|\bcontext\b", q):
        return (
            "bowling" if re.search(r"\bbowl|economy|wicket", q) else "batting"
        ), "true_performance needs the word 'true'"
    return None, ""


def dismissal_group(question: str) -> str | None:
    return "bowler_kind" if _SPIN_PACE_ALONE.search(question.lower()) else None


def partnership_group(question: str) -> str:
    q = question.lower()
    if re.search(r"\bpairs?\b|\bduos?\b|\bcombinations?\b", q):
        return "pair"
    if re.search(r"\bwicket\b", q):
        return "wicket"
    return "stand"


def auction_view(question: str, has_player: bool) -> str:
    q = question.lower()
    if re.search(r"\bcheap\w*|\balternatives?\b", q):
        return "cheapest"
    if re.search(
        r"\bactually played\b|\bplayed (?:any|matches|after)\b|\bbench(?:ed)?\b|\bdid .* play\b", q
    ):
        return "played"
    if re.search(
        r"\bmarket\b|\bvalue for money\b|\bmoneyball\b|\bover-?paid\b|\bunder-?paid\b|\buncapped\b|\bexpected to cost\b|\bworth\b|\bgroup\b",
        q,
    ):
        return "market"
    if has_player:
        return "player"
    return "predict"


def war_view(question: str) -> str | None:
    return (
        "projected"
        if re.search(
            r"\bproject\w*|\b2027\b|\bnext (?:season|ipl)\b|\bforecast\w*", question.lower()
        )
        else None
    )


def trade_view(question: str) -> str | None:
    return (
        "squad"
        if re.search(r"\bbest (?:xii|xi|11|12)\b|\bsquad\b", question.lower())
        and not re.search(r"\bswap|\btrad", question.lower())
        else None
    )


def scarcity_view(question: str) -> str | None:
    q = question.lower()
    if re.search(r"\bneeds?\b", q):
        return "team_needs"
    return "2027" if re.search(r"\b2027\b|\bnext auction\b|\bupcoming\b", q) else None


_NAME_IN_Q = re.compile(
    r"\bhow much (?:did|was|has|is) (.+?) (?:go|get|got|fetch|sell|sold|cost|fetched)\b|\bprice of (.+?)(?: in | at | for |$)",
    re.I,
)


def player_in_question(question: str, aliases) -> str | None:
    """A player the model left out: a known alias ('rohit', 'sky') or the name in 'how much did X go for'."""
    q = question.lower()
    for k in sorted(aliases, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", q):
            return k
    if m := _NAME_IN_Q.search(question):
        return (m.group(1) or m.group(2)).strip()
    return None
