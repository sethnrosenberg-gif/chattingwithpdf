"""Field extraction from posting text: pay, years, JD requirement, location bucket."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .textutil import snippet

# --------------------------------------------------------------------------- pay
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MONEY = r"(?:US\$|USD\s?\$?|\$)\s?" + _NUM + r"\s*([kKmM](?![a-z])|thousand)?"
_RANGE = re.compile(
    _MONEY + r"\s*(?:USD|usd)?\s*(?:-|–|—|to|and|through)\s*(?:US\$|USD\s?\$?|\$)?\s?" + _NUM + r"\s*([kKmM](?![a-z])|thousand)?",
)
_SINGLE = re.compile(_MONEY)
_PAY_CTX = re.compile(
    r"salary|base|pay|compensation|annual|range|wage|hiring range|rate|stipend|earn", re.I
)
_HOURLY = re.compile(r"per hour|/\s?hr\b|/\s?hour|hourly|an hour", re.I)
_MONTHLY = re.compile(r"per month|/\s?mo\b|/\s?month|monthly", re.I)
_OTE = re.compile(r"\bOTE\b|on[- ]target earnings|on target earnings|including commission|base \+ commission|commission", re.I)
_NYC_CTX = re.compile(r"new york|\bnyc\b|\bny\b", re.I)


@dataclass
class Pay:
    min: float | None = None
    max: float | None = None
    type: str = "not listed"  # base | OTE | hourly | not listed
    period: str | None = None
    currency: str | None = "USD"
    source: str = ""
    extras: str = ""


def _to_num(raw: str, suffix: str | None) -> float:
    v = float(raw.replace(",", ""))
    if suffix:
        s = suffix.lower()
        if s in ("k", "thousand"):
            v *= 1_000
        elif s == "m":
            v *= 1_000_000
    return v


def pay_extras(text: str) -> str:
    t = text.lower()
    bits = []
    if re.search(r"\bbonus", t):
        bits.append("bonus")
    if re.search(r"(equity|stock)[^.\n]{0,40}(grant|award|compensation|package|options|plan|incentive)|"
                 r"(offers?|plus|\+|and|with)\s+equity\b|\brsus?\b|stock options|equity (in|ownership)", t):
        bits.append("equity")
    if re.search(r"\bcommission", t):
        bits.append("commission")
    return " + ".join(bits)


def pay_from_text(text: str) -> Pay:
    """Regex fallback. Prefers ranges near pay words, and the NYC tier when tiers are listed."""
    if not text:
        return Pay()
    cands = []
    for m in _RANGE.finditer(text):
        lo = _to_num(m.group(1), m.group(2) or m.group(4))
        hi = _to_num(m.group(3), m.group(4) or m.group(2))
        # "$150-200K": apply trailing suffix to both ends
        if m.group(4) and not m.group(2) and lo < 1000 <= hi:
            lo = _to_num(m.group(1), m.group(4))
        if hi < lo:
            continue
        before = text[max(0, m.start() - 160) : m.start()]
        after = text[m.end() : m.end() + 60]
        ctx = before + " " + after
        period = "year"
        if _HOURLY.search(after) or _HOURLY.search(before[-40:]) or (hi < 1000 and not m.group(2) and not m.group(4)):
            period = "hour"
        elif _MONTHLY.search(after):
            period = "month"
        if period == "year" and not (20_000 <= lo <= 5_000_000 and hi <= 10_000_000):
            continue
        if period == "hour" and not (10 <= lo <= 2000):
            continue
        score = 0
        if _PAY_CTX.search(before[-120:]):
            score += 2
        if _NYC_CTX.search(before[-80:]):
            score += 1
        cands.append((score, m.start(), lo, hi, period, ctx))
    if cands:
        cands.sort(key=lambda c: (-c[0], c[1]))
        _, _, lo, hi, period, ctx = cands[0]
        ptype = "hourly" if period == "hour" else ("OTE" if _OTE.search(ctx) else "base")
        return Pay(lo, hi, ptype, period, "USD", "regex:range", pay_extras(text))
    # single figure only when clearly labelled as salary
    for m in _SINGLE.finditer(text):
        v = _to_num(m.group(1), m.group(2))
        before = text[max(0, m.start() - 70) : m.start()]
        if re.search(r"salary|base|compensation|pay", before, re.I) and 20_000 <= v <= 5_000_000:
            ptype = "OTE" if _OTE.search(before) else "base"
            return Pay(v, v, ptype, "year", "USD", "regex:single", pay_extras(text))
    return Pay(extras=pay_extras(text))


def pay_display(p: Pay) -> str:
    if p.min is None and p.max is None:
        return "Not listed"

    def fmt(v: float) -> str:
        if p.period == "hour":
            return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"
        if v >= 1_000_000:
            return f"${v / 1_000_000:.2f}M".replace(".00M", "M")
        if v % 1000 == 0:
            return f"${int(v / 1000)}K"
        return f"${v:,.0f}"

    rng = fmt(p.min) if p.min == p.max or p.max is None else f"{fmt(p.min)}–{fmt(p.max)}"
    if p.period == "hour":
        rng += "/hr"
    elif p.period == "month":
        rng += "/mo"
    label = {"base": " base", "OTE": " OTE", "hourly": ""}.get(p.type, "")
    extras = [e for e in (p.extras or "").split(" + ") if e and e != "commission"]
    return rng + label + ("" if not extras else " + " + " + ".join(extras))


# ------------------------------------------------------------------------- years
_WORDNUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
}
_YEARS = re.compile(
    r"(?:(?:minimum|at least|min\.?)\s+(?:of\s+)?)?"
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen)\b"
    r"(?:\s*\(\d{1,2}\))?"
    r"\s*(\+|plus)?\s*"
    r"(?:(?:-|–|to|or)\s*(\d{1,2})\s*(\+)?\s*)?"
    r"(?:full[- ]time\s+)?years?\b(?!\s+old)",
    re.I,
)


@dataclass
class YearsMention:
    lo: int
    hi: int | None
    context: str


def years_mentions(text: str) -> list[YearsMention]:
    out = []
    for m in _YEARS.finditer(text or ""):
        raw = m.group(1).lower()
        lo = _WORDNUM.get(raw) if raw in _WORDNUM else int(raw)
        hi = int(m.group(3)) if m.group(3) else None
        after = text[m.end() : m.end() + 90]
        before = text[max(0, m.start() - 60) : m.start()]
        before = re.split(r"[.;:\n]\s", before)[-1]  # same sentence only
        # keep mentions about experience, not "2-year program", "4 years ago", "25 years in business"
        if not re.search(r"experience|practice|practicing|work|working|of\s|in\s|as\s|post", after[:60], re.I):
            continue
        if re.search(r"program|founded|history|track record of|we've|we have|since|over the|in business", before + after[:30], re.I):
            continue
        if lo > 25:
            continue
        ctx = re.sub(r"\s+", " ", (before[-40:] + text[m.start() : m.end()] + after[:70])).strip()
        out.append(YearsMention(lo, hi, ctx))
    return out


def years_required(text: str) -> tuple[int | None, str]:
    ms = years_mentions(text)
    if not ms:
        return None, ""
    best = min(ms, key=lambda y: y.lo)
    return best.lo, best.context


# ---------------------------------------------------------------------------- JD
_JD_REQ = re.compile(
    r"(J\.?\s?D\.?|juris doctor|law degree)[^.\n]{0,40}\b(required|must|necessary)"
    r"|(must|required to)\s+(have|hold|possess)[^.\n]{0,40}(J\.?\s?D\.?|juris doctor|law degree)"
    r"|admitted to (practice|the bar)|member (in good standing )?of (the|a|at least one)[^.\n]{0,30}bar"
    r"|bar admission|licensed (to practice law|attorney)|active bar|good standing[^.\n]{0,40}bar",
    re.I,
)
_JD_ANY = re.compile(r"\bJ\.D\.|\bJD\b|juris doctor|law degree|law school|attorney|lawyer|legal background", re.I)
_JD_PREF = re.compile(
    r"(J\.?\s?D\.?|juris doctor|law degree|legal (training|background|education))[^.\n]{0,60}(preferred|a plus|plus|desirable|helpful|nice to have|advantage|welcome)"
    r"|(preferred|ideally|bonus)[^.\n]{0,60}(J\.?\s?D\.?|juris doctor|law degree)",
    re.I,
)


def jd_requirement(text: str, title: str = "") -> str:
    t = text or ""
    if _JD_REQ.search(t) or re.search(r"\b(attorney|counsel|lawyer)\b", title, re.I) and re.search(r"\bJ\.?D\.?\b|bar", t):
        return "Y"
    if _JD_PREF.search(t) or re.search(r"\bJ\.D\.|\bJD\b|juris doctor|law degree", t):
        return "pref"
    return "N"


# ---------------------------------------------------------------------- location
US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado",
    "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana",
    "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan", "MN": "minnesota",
    "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia", "PR": "puerto rico",
}
US_CITIES = (
    "san francisco|los angeles|chicago|boston|seattle|austin|dallas|houston|denver|miami|atlanta|"
    "washington|philadelphia|palo alto|menlo park|mountain view|san jose|san mateo|oakland|berkeley|"
    "stamford|greenwich|jersey city|hoboken|princeton|charlotte|nashville|salt lake|phoenix|portland|"
    "minneapolis|detroit|pittsburgh|baltimore|arlington|reston|mclean|tysons|west palm beach|palm beach|"
    "boca raton|fort lauderdale|tampa|orlando|raleigh|durham|columbus|cleveland|cincinnati|st\\.? louis|"
    "kansas city|san diego|irvine|santa monica|sacramento|las vegas|boulder|lehi|provo|wilmington|"
    "white plains|purchase|albany|buffalo|rochester|syracuse|long island|melville|short hills|newark|"
    "cambridge|burlington|waltham|new haven|hartford|richmond|norfolk|indianapolis|milwaukee|omaha|"
    "des moines|louisville|memphis|new orleans|birmingham|oklahoma city|tulsa|albuquerque|tucson|"
    "honolulu|anchorage|bethesda|rockville|silver spring|alexandria|plano|irving|fort worth|san antonio"
)
_NYC = re.compile(
    r"\bnew york(,?\s*(ny|new york|city|n\.y\.))?\b|\bnyc\b|\bmanhattan\b|\bbrooklyn\b|\bqueens\b|\bbronx\b|\bstaten island\b",
    re.I,
)
_NY_UPSTATE = re.compile(
    r"\b(albany|buffalo|rochester|syracuse|white plains|purchase|yonkers|tarrytown|armonk|rye|harrison|"
    r"melville|uniondale|mineola|garden city|hauppauge|long island|ithaca|binghamton|utica|schenectady|"
    r"poughkeepsie|valhalla|new york state)\b",
    re.I,
)
_REMOTE = re.compile(r"\bremote\b|\banywhere\b|work from home|\bwfh\b|distributed|virtual", re.I)
_US_MARK = re.compile(r"\bUS\b|\bU\.S\.|\bUSA\b|united states|north america|\bamericas\b|nationwide|us-based", re.I)
NON_US = (
    "united kingdom|\\buk\\b|england|london|edinburgh|glasgow|manchester|ireland|dublin|canada|toronto|"
    "vancouver|montreal|calgary|ottawa|mexico|brazil|são paulo|sao paulo|argentina|buenos aires|colombia|bogota|"
    "chile|peru|germany|berlin|munich|frankfurt|hamburg|france|paris|spain|madrid|barcelona|portugal|lisbon|"
    "italy|milan|rome|netherlands|amsterdam|belgium|brussels|luxembourg|switzerland|zurich|geneva|austria|vienna|"
    "sweden|stockholm|norway|oslo|denmark|copenhagen|finland|helsinki|poland|warsaw|krakow|czech|prague|"
    "hungary|budapest|romania|bucharest|greece|athens|turkey|istanbul|israel|tel aviv|uae|dubai|abu dhabi|"
    "saudi|riyadh|qatar|doha|india|bangalore|bengaluru|mumbai|delhi|gurgaon|gurugram|hyderabad|pune|chennai|"
    "singapore|hong kong|china|shanghai|beijing|shenzhen|taiwan|taipei|japan|tokyo|korea|seoul|australia|"
    "sydney|melbourne|new zealand|auckland|philippines|manila|vietnam|indonesia|jakarta|malaysia|"
    "kuala lumpur|thailand|bangkok|south africa|cape town|johannesburg|nigeria|lagos|kenya|nairobi|egypt|"
    "emea|apac|latam|europe|european|\\beu\\b|cayman|bermuda|jersey, channel|guernsey|\\bldn\\b|\\bhkg\\b|\\bsgp\\b"
)
_NON_US = re.compile(NON_US, re.I)
_US_CITY = re.compile(r"\b(" + US_CITIES + r"|dc|d\.c\.)(?![a-z])", re.I)
_STATE_ABBR = re.compile(r"(?:,|\s)\s*(" + "|".join(US_STATES) + r")\b(?:\s*\d{5})?(?:\s*,?\s*(?:US|USA|United States))?\s*$")
_STATE_NAME = re.compile(r"\b(" + "|".join(sorted(US_STATES.values(), key=len, reverse=True)) + r")\b", re.I)

BUCKET_RANK = {"nyc": 0, "us_remote": 1, "us_other": 2, "unknown": 3, "non_us": 4}


def classify_location(loc: str, *, remote_flag: bool | None = None, country: str | None = None) -> str:
    s = (loc or "").strip()
    if not s:
        if remote_flag and (country is None or re.match(r"^(US|USA|United States)", country or "", re.I)):
            return "us_remote"
        if country and not re.match(r"^(US|USA|United States)", country, re.I):
            return "non_us"
        return "unknown"
    is_remote = bool(_REMOTE.search(s)) or bool(remote_flag)
    non_us = bool(_NON_US.search(s)) or bool(country and not re.match(r"^(US|USA|United States)", country, re.I))
    if _NYC.search(s) and not _NY_UPSTATE.search(s) and not re.search(r"new york state", s, re.I):
        return "nyc"
    us = bool(_US_MARK.search(s) or _US_CITY.search(s) or _STATE_ABBR.search(s) or _STATE_NAME.search(s))
    if is_remote:
        if non_us and not _US_MARK.search(s):
            return "non_us"
        return "us_remote"
    if us and not (non_us and not _US_MARK.search(s)):
        return "us_other"
    if non_us:
        return "non_us"
    return "unknown"


def best_bucket(locs: list[str], *, remote_flag: bool | None = None, country: str | None = None) -> str:
    parts = [x for l in locs if l for x in re.split(r"\s+or\s+|;|\s/\s", l) if x.strip()]
    buckets = [classify_location(l, remote_flag=remote_flag, country=country) for l in parts]
    # a bare "Remote" next to a non-US office is that country's remote, not US remote
    if "non_us" in buckets and "nyc" not in buckets and "us_other" not in buckets:
        buckets = [("non_us" if b == "us_remote" and not _US_MARK.search(p) else b) for b, p in zip(buckets, parts)]
    buckets = buckets or [
        classify_location("", remote_flag=remote_flag, country=country)
    ]
    return min(buckets, key=lambda b: BUCKET_RANK[b])


def workplace_of(text: str) -> str:
    t = (text or "").lower()
    if "hybrid" in t:
        return "hybrid"
    if re.search(r"\bremote\b", t):
        return "remote"
    if re.search(r"on[- ]?site|in[- ]office|in office", t):
        return "onsite"
    return ""


__all__ = [
    "Pay", "pay_from_text", "pay_display", "pay_extras", "years_required", "years_mentions",
    "jd_requirement", "classify_location", "best_bucket", "workplace_of", "snippet",
]
