"""The CLAUDE.md rubric: hard excludes, fit signals, bucket.

Rules run on every posting. Judgment calls (sales-attached, domain-years floor, litigation
accepted) come from subagent judgments cached in data/judgments.jsonl when available, and
from conservative regex approximations otherwise.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import config
from .extract import years_mentions
from .keywords import flags
from .models import Posting
from .textutil import snippet

PIPELINE = ("marqeta", "harvey", "hebbia", "norm ai", "normai", "general legal")
JUDGMENTS = config.DATA / "judgments.jsonl"
FIT_MIN = 3  # signals needed for the fit table

RX = {
    "clerkship": re.compile(r"clerkship|judicial clerk", re.I),
    "litigation": re.compile(r"litigat(ion|or|ing)[^.\n]{0,60}(experience|background|practice|skills)|(experience|background)[^.\n]{0,60}litigat|former litigators?|litigators?", re.I),
    "fs_background": re.compile(r"financial services|financial institution|broker[- ]dealer|bank(ing)? (experience|background|regulat)|capital markets experience", re.I),
    "research_for_decisions": re.compile(r"(research|analy[sz]|memo|advis|interpret|assess)[^.\n]{0,80}(regulat|legal|law|polic|rule)|(regulat|legal|polic)[^.\n]{0,80}(research|analysis|memo|advice|advis|guidance)", re.I),
    "teaches_finance": re.compile(r"no (prior |previous )?(finance|financial|investing) (experience|background|knowledge)|no previous finance|we(’|')?ll teach|we will teach|training program|\bacademy\b|rotational program|no prior experience (in|with) (finance|investing)", re.I),
    "credit": re.compile(r"\bcredit\b|distressed|bankruptcy|restructuring|covenant|leveraged loan|high[- ]yield|special situations|\bLME\b|liability management|chapter 11", re.I),
    "fintech": re.compile(r"fintech|payments?\b|crypto|digital assets?|stablecoin|blockchain|\bAI\b|artificial intelligence|machine learning|\bLLMs?\b|market structure|prediction markets?|exchange|trading", re.I),
}
EXCL = {
    "sales_title": re.compile(r"account executive|\bsales\b|pre-?sales|solutions (engineer|consultant)|business development rep", re.I),
    "demo": re.compile(r"(run|deliver|lead|conduct)[^.\n]{0,30}demos?|pre-?sales|prospects?\b|sales (cycle|team|process|pipeline)|close deals|quota", re.I),
    "quant_title": re.compile(r"\bquant|quantitative research|data scien|statistician|machine learning", re.I),
    "python": re.compile(r"python[^.\n]{0,60}(required|must|proficien)|(proficien|fluen|expert|strong)[^.\n]{0,40}(python|statistic|econometric)", re.I),
    "er_banking": re.compile(r"\b([5-9]|1\d)\s*\+?\s*(\+|or more)?\s*years?[^.\n]{0,90}(equity research|investment banking|\bbanking\b|buy[- ]side|hedge fund|private equity|investment (research|experience|analyst)|fundamental (equity|investing))", re.I),
    "comp_ops_title": re.compile(r"paralegal|document review|compliance (analyst|specialist|associate|officer|operations)|\bkyc\b|\baml\b|surveillance|legal (assistant|secretary)|docketing", re.I),
    "contract": re.compile(r"\bcontract(or)?\b[^.\n]{0,40}(role|position|basis|engagement)|part[- ]time|\bfreelance\b|\b\d+[- ]week\b", re.I),
}
LAWYER_TITLE = re.compile(r"counsel|attorney|lawyer|legal", re.I)
# in-house practice areas outside what he wants (CLAUDE.md: no generic transactional/admin seats)
OFF_TARGET_PRACTICE = re.compile(
    r"employment|labor|real estate|commercial|corporate|securities|\bM&A\b|mergers|transactions?\b|\bIP\b|intellectual property|"
    r"patent|trademark|\btax\b|benefits|immigration|procurement|contracts?\b|privacy(?! ?& ?regulatory| and regulatory)|"
    r"capital markets|venture|emerging companies|investment funds|funds? formation|real assets|energy|healthcare|entertainment",
    re.I,
)
TARGET_PRACTICE = re.compile(r"regulat|policy|risk|payments|credit|litigation|investigat|enforcement|compliance counsel|product counsel|governance|crypto|digital asset|stablecoin|derivatives|market", re.I)
LAW_FIRM_ASSOCIATE = re.compile(r"\bbillable|our (attorneys|lawyers|clients)|law firm associate|join our [\w ]*(practice|group)|am ?law", re.I)


def desc_hash(p: Posting) -> str:
    return hashlib.sha1((p.title + "\n" + p.description[:20000]).encode("utf-8", "ignore")).hexdigest()[:16]


_judg: dict[str, dict] | None = None


def _role_key(company: str, title: str) -> str:
    from .textutil import norm_company, norm_title

    return f"role:{norm_company(company)}|{norm_title(title)}"


def judgments() -> dict[str, dict]:
    """Latest judgment per posting key, plus a company+title index so re-posted roles reuse it."""
    global _judg
    if _judg is None:
        _judg = {}
        if JUDGMENTS.exists():
            from .db import get_posting

            for line in JUDGMENTS.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    _judg[d["key"]] = d
                    if (p := get_posting(d["key"])):
                        _judg[_role_key(p.company, p.title)] = d
    return _judg


SEAT_FAMILIES = [  # CLAUDE.md: the seat families that loosen the Stage 2 domain-years screen
    ("litigation-finance underwriting", r"underwrit", r"litigation_finance|legal assets|litigation financ"),
    ("legal-AI research/build seat", r"applied legal research|legal research|legal engineer|r&d attorney|legal fellow", r"legal_ai|legal ai|\bai\b"),
    ("business-side regulatory risk", r"regulatory (risk|exam|engagement|relations)|regulatory risk", r""),
    ("employer-run finance academy", r"academy|rotational|investment analyst program|client investment research", r""),
    ("embedded qualitative research", r"fundamental research|market intelligence|\bcanvas\b", r""),
]


def seat_family(p: Posting) -> str:
    ctx = f"{p.company} {p.segment or ''} {p.description[:3000]}"
    for name, title_rx, ctx_rx in SEAT_FAMILIES:
        if re.search(title_rx, p.title, re.I) and (not ctx_rx or re.search(ctx_rx, ctx, re.I)):
            return name
    return ""


def is_pipeline(company: str) -> bool:
    c = company.lower()
    return any(c.startswith(x) for x in PIPELINE)


def score(p: Posting) -> Posting:
    text = p.description or ""
    title = p.title
    both = title + "\n" + text
    j = judgments().get(p.key) or judgments().get(_role_key(p.company, p.title))
    sig: list[str] = []
    excl: list[str] = []
    poor: list[str] = []

    # ------------------------------------------------------------ hard excludes
    if p.pay_type == "OTE" or re.search(r"\bOTE\b|on[- ]target earnings", both):
        excl.append("Pay is quoted as OTE (variable-heavy)")
    sales = (j or {}).get("sales_attached")
    if sales is None:
        sales = "Y" if (EXCL["sales_title"].search(title) or (re.search(r"legal engineer|solutions", title, re.I) and EXCL["demo"].search(text))) else "N"
    p.sales_attached = sales
    if sales == "Y":
        q = (j or {}).get("rationale") or snippet(text, EXCL["demo"]) or title
        excl.append(f"Sales-attached / demo-led role: {q}")
    if "6+ years leveraged finance" in flags(text):
        excl.append("Asks for 6+ years of leveraged-finance or transactional practice: " + snippet(text, r"\b([6-9]|1\d)\+?[^.\n]{0,80}(leveraged finance|transactional|finance practice)"))
    if EXCL["quant_title"].search(title) or EXCL["python"].search(text):
        excl.append("Requires Python, statistics or quant work: " + (snippet(text, EXCL["python"]) or title))
    if EXCL["er_banking"].search(text):
        excl.append("Asks for 5+ years of equity research, banking or buy-side: " + snippet(text, EXCL["er_banking"]))
    ym = years_mentions(text)
    if any(y.lo >= 10 for y in ym):
        y = next(y for y in ym if y.lo >= 10)
        excl.append(f"Asks for 10+ years: “{y.context}”")
    if EXCL["comp_ops_title"].search(title) and not re.search(r"counsel|attorney", title, re.I):
        excl.append("Paralegal, document review or compliance-operations role")
    if j and j.get("hard_exclude"):
        excl.append(j["hard_exclude"])

    # --------------------------------------------------------------- fit signals
    if p.jd_required in ("Y", "pref") or (j or {}).get("jd") in ("Y", "pref"):
        sig.append("JD required/preferred")
    if RX["clerkship"].search(text):
        sig.append("clerkship valued")
    lit = (j or {}).get("litigation_accepted")
    p.litigation_accepted = lit or ("Y" if RX["litigation"].search(text) else "unclear")
    if p.litigation_accepted == "Y":
        sig.append("litigation experience accepted")
    if RX["fs_background"].search(text):
        sig.append("financial-services background a plus")
    if RX["research_for_decisions"].search(both):
        sig.append("regulatory/legal/policy research for decisions")
    if RX["teaches_finance"].search(both):
        sig.append("employer teaches the finance")
    if RX["credit"].search(both):
        sig.append("credit/distressed/bankruptcy subject")
    if RX["fintech"].search(both):
        sig.append("fintech/crypto/AI/market-structure subject")
    if p.pay_type == "base" and p.pay_min and ((p.pay_min + (p.pay_max or p.pay_min)) / 2) >= 150_000:
        sig.append("base pay midpoint ≥ $150K")
    if p.years_required is not None and 2 <= p.years_required <= 5:
        sig.append(f"{p.years_required} years required (2–5 band)")

    # ------------------------------------------------------ poor-match (not hard)
    floor = (j or {}).get("meets_floor")
    fy = (j or {}).get("domain_floor_years")
    dom = (j or {}).get("domain") or ""
    if floor == "N" or (isinstance(fy, int) and fy >= 6):
        poor.append((f"Asks for {fy}+ years of {dom}" if fy else f"Wants {dom} experience he doesn't have")
                    + (f": {j['rationale']}" if j.get("rationale") else ""))
    elif dom and OFF_TARGET_PRACTICE.search(dom) and not TARGET_PRACTICE.search(dom):
        poor.append(f"Generalist or off-target practice seat (wants {dom})")
    elif not j and p.years_required is not None and p.years_required >= 6:
        poor.append(f"Asks for {p.years_required}+ years: “{p.years_text}”")
    if ym and max((y.hi or y.lo) for y in ym) <= 2 and p.years_required is not None and p.years_required <= 1:
        poor.append(f"Pitched at {p.years_required}–{max((y.hi or y.lo) for y in ym)} years of experience")
    t_core = re.sub(r"\s*@.*$", "", title)  # "Counsel @ Riskified": the employer name isn't the practice area
    if (LAWYER_TITLE.search(t_core) or re.search(r"\bassociate\b", t_core, re.I)) and OFF_TARGET_PRACTICE.search(t_core) and not TARGET_PRACTICE.search(t_core):
        poor.append(f"Practice area outside the target seats ({OFF_TARGET_PRACTICE.search(t_core).group(0).lower()} work)")
    if re.search(r"\bassociate\b", title, re.I) and LAW_FIRM_ASSOCIATE.search(text) and not re.search(r"underwrit|research|analyst", title, re.I):
        poor.append("Law-firm associate seat (billable practice, court time)")
    if p.pay_type == "hourly" or EXCL["contract"].search(title + " " + text[:1500]):
        poor.append("Contract, hourly or part-time engagement" + (f" ({p.pay_display})" if p.pay_type == "hourly" else ""))

    p.fit_signals = sig
    p.fit_score = len(sig)
    p.hard_exclude_reason = excl[0] if excl else ""
    family = seat_family(p)
    if family:
        p.fit_signals = sig + [f"seat family: {family}"]  # shown in jobs.csv; not counted as a rubric signal
    if not p.hard_exclude_reason and not poor and p.fit_score < FIT_MIN and not family:
        poor.append(f"Weak fit: {p.fit_score} of 10 signals" + (f" ({', '.join(sig)})" if sig else ""))
    p.poor_reason = p.hard_exclude_reason or "; ".join(poor)
    p.domain_floor = ((f"{fy}+ yrs " if fy is not None else "") + f"{dom} (meets: {floor})") if dom else ""
    p.judgment_rationale = (j or {}).get("rationale", "")
    p.pipeline = is_pipeline(p.company)

    if p.status != "open":
        p.bucket = "closed"
    elif p.loc_bucket not in ("nyc", "us_remote"):
        p.bucket = "outside" if p.loc_bucket in ("us_other", "unknown") else "irrelevant"
    elif p.poor_reason:
        # the markdown poor-match table keeps target-family seats and near-fits; the long tail stays in jobs.csv
        from .keywords import title_families

        strong = [f for f in title_families(title) if f not in ("counsel/attorney", "regulatory (other)", "policy (other)", "litigation")]
        p.bucket = "poor" if (p.fit_score >= 3 or strong or "seed" in p.sources) else "low"
    else:
        p.bucket = "fit"
    return p
