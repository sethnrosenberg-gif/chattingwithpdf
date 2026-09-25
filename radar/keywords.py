"""Keyword families from the kickoff spec, used to decide which postings are worth scoring.

relevance() answers "should this posting be in the output at all?" Scoring (fit vs poor match)
happens later in radar.score. Titles that are clearly off-target (engineers, sales reps,
paralegals) are dropped here and only counted in the run log.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- include: titles
TITLE_FAMILIES: list[tuple[str, str]] = [
    ("legal analyst", r"\blegal analyst"),
    ("bankruptcy", r"bankruptcy"),
    ("restructuring", r"restructuring"),
    ("LME", r"\bLME\b|liability management"),
    ("covenant", r"covenant"),
    ("legal-assets underwriting", r"underwrit"),
    ("applied legal research", r"applied legal research|legal research(er)?\b"),
    ("legal engineer", r"legal engineer"),
    ("regulatory risk", r"regulatory risk"),
    ("regulatory relations", r"regulatory relations|regulator relations|regulatory engagement|regulatory exam"),
    ("regulatory strategy", r"regulatory (strategy|policy|affairs|advisory|change)"),
    ("policy analyst/counsel", r"policy (analyst|counsel|associate|advisor|lead|manager|director|research)|public policy"),
    ("product counsel", r"product counsel"),
    ("payments counsel", r"payments? counsel"),
    ("regulatory counsel", r"regulatory counsel"),
    ("AI governance counsel", r"\bai\b.*(governance|policy).*counsel|(governance|policy).*\bai\b.*counsel|ai governance"),
    ("market intelligence", r"market intelligence"),
    ("fundamental researcher", r"fundamental research"),
    ("research associate", r"research associate|investment research"),
    ("investment analyst program", r"(investment )?analyst program|academy|associate program|rotational"),
    ("experienced professionals", r"experienced professionals?"),
    # broader legal seats for a JD: counsel/attorney/lawyer titles
    ("counsel/attorney", r"\bcounsel\b|\battorney\b|\blawyer\b|\bsolicitor\b|legal (expert|specialist|advisor|lead|manager|director|editor|writer|reporter)|general counsel"),
    ("credit research/risk", r"credit (risk|review|officer|research|analyst|strategist)|distressed|special situations|event[- ]driven|merger arb|risk arbitrage"),
    ("investigations", r"investigations? (counsel|analyst|associate|lead|manager)|investigative (research|analyst|reporter)"),
    ("regulatory (other)", r"\bregulat\w+"),
    ("policy (other)", r"\bpolicy\b"),
    ("litigation", r"litigation"),
]
_TITLE_RX = [(label, re.compile(rx, re.I)) for label, rx in TITLE_FAMILIES]

# titles that need finance context before a generic match counts
_NEEDS_FINANCE = {"policy analyst/counsel", "regulatory (other)", "research associate", "policy (other)"}
# underwriting counts only for legal assets (litigation finance), per the spec
_NEEDS_LEGAL = {"legal-assets underwriting"}
_LEGAL_CTX = re.compile(r"litigation|legal assets?|legal finance|patent|arbitration|lawsuit|law firm|litigation_finance", re.I)
# operations/support seats are out of scope unless a strong legal/research family matched
_OPS = re.compile(r"operations|\bops\b|support|onboarding|\bkyc\b|\baml\b|servicing|processing|settlement|reconciliation|fund accounting|regulatory reporting|reporting (analyst|specialist|manager)", re.I)
# domain phrases (crypto, distressed...) make a posting relevant only for knowledge-work titles
_KNOWLEDGE_TITLE = re.compile(r"research|analyst|counsel|attorney|legal|policy|regulat|risk|investment|strategist|underwrit|intelligence|investigat|editor|writer|reporter|expert", re.I)
_STRONG_DESC = {"clerkship", "J.D.", "law degree", "no finance experience", "litigation finance"}
# seats a description phrase must not pull in: product, data, design, security, finance-ops and go-to-market work
_NOT_KNOWLEDGE = re.compile(
    r"\bdata\b|product (analyst|manager|designer)|\bux\b|user research|design|\bgtm\b|go-to-market|growth|treasury|finops|"
    r"accounting|security|secops|technical|architect|reporting|planning|coordinator|payment risk|fraud|control desk|trader|"
    r"sales|partnerships?|business development|recruit|people|hr\b|operations|analytics",
    re.I,
)
_FINANCE_CTX = re.compile(
    r"financ|bank|capital markets|securities|fintech|payments?|crypto|digital assets?|stablecoin|trading|"
    r"exchange|broker|asset manage|fund|investment|credit|lending|insurance|derivatives|market structure",
    re.I,
)

# ------------------------------------------------------------ include: description
DESC_PHRASES: list[tuple[str, str]] = [
    ("clerkship", r"clerkship|judicial clerk"),
    ("J.D.", r"\bJ\.D\.|\bJD\b|juris doctor"),
    ("law degree", r"law degree|law school"),
    ("no finance experience", r"no (prior |previous )?(finance|financial) (experience|background|knowledge)|no previous finance"),
    ("financial services background", r"financial services (background|experience|industry)"),
    ("prediction markets", r"prediction markets?"),
    ("digital assets", r"digital assets?"),
    ("stablecoin", r"stablecoin"),
    ("event-driven", r"event[- ]driven"),
    ("special situations", r"special situations"),
    ("distressed", r"\bdistressed\b"),
    ("litigation finance", r"litigation financ|legal finance|litigation funding"),
]
_DESC_RX = [(label, re.compile(rx, re.I)) for label, rx in DESC_PHRASES]

# a description phrase only makes a posting relevant when the title is a research/legal/policy-type seat
ROLE_BROAD = re.compile(
    r"analyst|associate|research|counsel|attorney|lawyer|legal|policy|regulat|risk|underwrit|investment|"
    r"investigat|intelligence|advisor|strategist|editor|reporter|writer|fellow|program|expert|specialist|"
    r"principal|vice president|\bvp\b|director",
    re.I,
)

# ------------------------------------------------------------------- drop outright
TITLE_DROP = re.compile(
    r"paralegal|legal assistant|legal secretary|docketing|document review|legal operations (specialist|coordinator)|"
    r"account executive|\bSDR\b|\bBDR\b|sales development|business development rep|inside sales|"
    r"software|developer|\bSRE\b|site reliability|devops|data (engineer|scientist)|machine learning engineer|"
    r"(?<!legal )engineer(ing)?\b(?! (manager, )?legal)|designer|recruit(er|ing)|talent acquisition|"
    r"payroll|accounts payable|bookkeep|receptionist|executive assistant|administrative assistant|office manager|"
    r"facilities|help ?desk|it support|intern\b|internship|summer analyst|campus|new grad|"
    r"customer (success|support|service)|marketing|brand|social media|graphic|video|copywriter",
    re.I,
)
# "legal engineer" and "solutions engineer, legal" style titles survive TITLE_DROP via the lookarounds above;
# rows that survive but are sales-attached are caught by the rubric (hard exclude).

# ------------------------------------------------------------------- flag phrases
FLAGS: list[tuple[str, str]] = [
    ("OTE", r"\bOTE\b|on[- ]target earnings"),
    ("quota", r"\bquota\b"),
    ("account executive", r"account executive"),
    ("pre-sales", r"pre[- ]?sales|presales|sales engineer|solutions engineer"),
    ("demo", r"\bdemos?\b|demonstrations? (of|to) (prospects|customers)"),
    ("Agile", r"\bagile\b"),
    ("Scrum", r"\bscrum\b"),
    ("Python required", r"python[^.\n]{0,60}(required|must|proficien)|(proficien|fluen|expert)[^.\n]{0,40}python"),
    ("earnings models", r"earnings models?|financial model(l)?ing|build (and maintain )?(detailed )?(financial )?models"),
    ("waterfall model", r"waterfall model"),
    ("6+ years leveraged finance", r"\b([6-9]|1\d)\+?\s*(\+|or more)?\s*years?[^.\n]{0,60}(leveraged finance|lev ?fin|finance practice|transactional)"),
    ("paralegal", r"\bparalegal"),
    ("document review", r"document review"),
    ("10+ years", r"\b(1\d|[2-9]\d)\s*\+?\s*(\+|or more)?\s*years"),
]
_FLAG_RX = [(label, re.compile(rx, re.I)) for label, rx in FLAGS]


def title_families(title: str) -> list[str]:
    return [label for label, rx in _TITLE_RX if rx.search(title or "")]


def desc_phrases(text: str) -> list[str]:
    return [label for label, rx in _DESC_RX if rx.search(text or "")]


def flags(text: str) -> list[str]:
    return [label for label, rx in _FLAG_RX if rx.search(text or "")]


def relevance(title: str, description: str = "", company_segment: str | None = None) -> tuple[bool, str]:
    """(relevant?, reason). Reason names the keyword family that matched, or why it was dropped."""
    t = title or ""
    if TITLE_DROP.search(t) and not re.search(r"legal engineer|counsel|attorney|lawyer", t, re.I):
        return False, "title dropped: " + TITLE_DROP.search(t).group(0)
    fams = title_families(t)
    ctx = f"{t}\n{description[:6000] if description else ''}\n{company_segment or ''}"
    fams = [f for f in fams if f not in _NEEDS_LEGAL or _LEGAL_CTX.search(ctx)]
    strong = [f for f in fams if f not in _NEEDS_FINANCE]
    if strong:
        return True, "title: " + ", ".join(strong)
    if _OPS.search(t):
        return False, "title dropped: operations/support seat"
    if fams and _FINANCE_CTX.search(ctx):
        return True, "title: " + ", ".join(fams) + " (finance context)"
    if ROLE_BROAD.search(t) and not _NOT_KNOWLEDGE.search(t):
        ph = desc_phrases(description)
        if any(p in _STRONG_DESC for p in ph) or (ph and _KNOWLEDGE_TITLE.search(t)):
            return True, "description: " + ", ".join(ph)
    return False, "no keyword family matched"
