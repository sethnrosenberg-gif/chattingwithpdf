"""HTML-to-text, JSON-LD, and normalization helpers."""
from __future__ import annotations

import html as htmllib
import json
import re
import unicodedata

from selectolax.parser import HTMLParser

_BLOCK_TAGS = ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "ul", "ol")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    if "<" not in s and "&" in s:
        s = htmllib.unescape(s)
    if "&lt;" in s and "<" not in s:  # Greenhouse double-escapes content
        s = htmllib.unescape(s)
    tree = HTMLParser(s)
    for tag in ("script", "style", "noscript"):
        for n in tree.css(tag):
            n.decompose()
    for tag in _BLOCK_TAGS:
        for n in tree.css(tag):
            if tag == "li":
                n.insert_before("\n- ")
            else:
                n.insert_before("\n")
            n.insert_after("\n")
    text = tree.body.text(separator="") if tree.body else tree.text(separator="")
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def jsonld_objects(html: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        raw = m.group(1).strip()
        try:
            d = json.loads(raw)
        except ValueError:
            try:
                d = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except ValueError:
                continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            it = stack.pop()
            if isinstance(it, dict):
                out.append(it)
                if isinstance(it.get("@graph"), list):
                    stack.extend(it["@graph"])
            elif isinstance(it, list):
                stack.extend(it)
    return out


def jsonld_jobposting(html: str) -> dict | None:
    for it in jsonld_objects(html):
        t = it.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            return it
    return None


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


_CO_SUFFIX = re.compile(
    r"\b(inc|llc|l\.?p|lp|ltd|limited|corp|corporation|co|company|group|holdings|plc|n\.?a|the)\b\.?", re.I
)


def norm_company(s: str) -> str:
    s = ascii_fold(s or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = _CO_SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


_TITLE_NOISE = re.compile(
    r"\s*[-–—|,(]\s*(new york|nyc|ny|remote|us|usa|united states|hybrid|san francisco|london|chicago|washington|dc)\b.*$",
    re.I,
)


def norm_title(s: str) -> str:
    s = ascii_fold(s or "").lower().strip()
    s = _TITLE_NOISE.sub("", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\bsr\b\.?", "senior", s)
    s = re.sub(r"\bvp\b", "vice president", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def snippet(text: str, pattern: str | re.Pattern, width: int = 110) -> str:
    """Return a short quote around the first match, for rationales."""
    rx = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, re.I)
    m = rx.search(text or "")
    if not m:
        return ""
    a = max(0, m.start() - width // 2)
    b = min(len(text), m.end() + width // 2)
    q = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a > 0 else "") + q + ("…" if b < len(text) else "")
