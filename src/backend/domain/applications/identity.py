"""
Identity matching — faithful port of profile/job-search/dashboard/lib/identity.js.

A job is company + canonical title, not a posting id, so reposts fold into one
row and Richard's review notes survive. Pure functions, no I/O — this is the
one piece of the dashboard migration that must not regress, so it is ported
line-for-line rather than "improved."

Two quirks in the original are reproduced deliberately, not fixed, because
existing production data already depends on them (see
tests/domain/applications/test_identity.py for the cases that pin them down):

1. TITLE_SYNONYMS["fde"] expands to a 3-word phrase ("forward deployed
   engineer"). If a title already spells the phrase out next to the
   abbreviation (e.g. "Forward Deployed Engineer (FDE)"), the words appear
   twice in the normalized title. A real migrated row has this exact
   duplication baked into its identity_key.
2. norm_company collapses "SA" (undotted) into a noise word but not "S.A."
   (dotted) — the dots split it into two single-letter tokens ("s", "a")
   that COMPANY_NOISE doesn't list. "Qubika S.A." and "Qubika" are therefore
   NOT recognized as the same company, while "Qubika SA" would be.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

Role = Mapping[str, Any]

COMPANY_NOISE: frozenset[str] = frozenset(
    {
        "inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company",
        "sa", "sac", "sas", "srl", "spa", "gmbh", "bv", "nv", "ag", "plc", "pte",
        "sl", "sarl", "oy", "ab", "as", "kk", "pvt", "private",
        "careers", "career", "jobs", "hiring", "recruiting", "recruitment",
        "talent", "group", "holdings", "technologies", "technology", "tech",
        "solutions", "services", "consulting", "labs", "software", "systems",
        "global", "international", "worldwide", "usa", "us", "latam",
    }
)

TITLE_SYNONYMS: dict[str, str] = {
    "sr": "senior", "snr": "senior", "jr": "junior", "mid": "mid",
    "eng": "engineer", "engr": "engineer", "dev": "developer", "developer": "engineer",
    "fullstack": "full stack", "fullystack": "full stack",
    "ml": "machine learning", "ai/ml": "ai machine learning",
    "fde": "forward deployed engineer",
    "ii": "2", "iii": "3", "iv": "4", "i": "1",
}

TITLE_STOP: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "for", "and", "or", "to", "in", "at", "with",
        "remote", "hybrid", "onsite", "on", "site", "position", "role", "opening",
        "new", "urgent", "immediate", "hiring", "wfh", "anywhere",
    }
)

MEANINGLESS: frozenset[str] = frozenset({"engineer", "senior", "ai", "developer", "1", "2", "3", "software"})

STRONG = 0.95
"""Same-company title similarity at or above this is treated as the same job."""

DEFAULT_THRESHOLD = 0.70
"""Same-company title similarity at or above this (but below STRONG) is a 'near' hit, reported not folded."""

_ACCENTS_RE = re.compile(r"[̀-ͯ]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_COMPANY_SUFFIX_RE = re.compile(r"\b(client|via|formerly|dba|aka)\b.*$")
_REQ_ID_RE = re.compile(r"\b(irc|jr|req|job|id|ref)[-_ ]?\d{3,}\b")
_BRACKET_ID_RE = re.compile(r"[#(\[]\s*[a-z]*[-_ ]?\d{3,}[^)\]]*[)\]]?")
_GEO_TAIL_RE = re.compile(
    r"[\s,\-–—|(]+(remote|hybrid|on[- ]?site|latam|latin america|"
    r"south america|americas|brazil|brasil|mexico|peru|colombia|argentina|"
    r"chile|usa|u s|united states|worldwide|global|anywhere)[\s,)\]]*$"
)
_TITLE_CHARS_RE = re.compile(r"[^a-z0-9+/]+")


def strip_accents(value: Optional[str]) -> str:
    return _ACCENTS_RE.sub("", unicodedata.normalize("NFD", value or ""))


def base_norm(value: Optional[str]) -> str:
    return _NON_ALNUM_RE.sub(" ", strip_accents(value).lower()).strip()


def norm_company(value: Optional[str]) -> str:
    """Lowercase, strip legal-entity/recruiting noise words. Never returns empty if input wasn't."""
    text = _COMPANY_SUFFIX_RE.sub("", base_norm(value)).strip()
    words = text.split(" ")
    kept = [w for w in words if w and w not in COMPANY_NOISE]
    return " ".join(kept if kept else words).strip()


def norm_title(value: Optional[str]) -> str:
    text = strip_accents(value).lower()
    text = _REQ_ID_RE.sub(" ", text)
    text = _BRACKET_ID_RE.sub(" ", text)
    text = _GEO_TAIL_RE.sub(" ", text)
    text = _TITLE_CHARS_RE.sub(" ", text).strip()

    out: list[str] = []
    for word in text.split(" "):
        if not word:
            continue
        word = TITLE_SYNONYMS.get(word, word)
        for part in word.split(" "):
            if part and part not in TITLE_STOP:
                out.append(part)
    return " ".join(out)


def identity_key(role: Role) -> str:
    return f"{norm_company(role.get('company'))}::{norm_title(role.get('title'))}"


def title_tokens(title: Optional[str]) -> frozenset[str]:
    return frozenset(w for w in norm_title(title).split(" ") if w and w not in MEANINGLESS)


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Jaccard similarity over meaningful title tokens, falling back to exact-string equality
    when either side reduces to no meaningful tokens at all."""
    tokens_a, tokens_b = title_tokens(a), title_tokens(b)
    if not tokens_a or not tokens_b:
        return 1.0 if norm_title(a) == norm_title(b) else 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


class MatchKind(str, Enum):
    POSTING = "posting"
    EXACT = "exact"
    NEAR = "near"


@dataclass(frozen=True)
class MatchResult:
    role: Role
    kind: MatchKind
    score: float


def find_match(role: Role, roles: Sequence[Role], threshold: float = DEFAULT_THRESHOLD) -> Optional[MatchResult]:
    """
    Three tiers, each a separate full pass over `roles`, in this exact order:
      1. identical posting id (own id, or nested in any candidate's postings[])
      2. identical identity_key (prefer the candidate's stored key; else recompute)
      3. same normalized company + title-similarity fallback — first hit >= STRONG
         wins immediately ("exact"); otherwise the single best-scoring candidate
         >= threshold is kept as a "near" hit.
    Returns None when nothing matches (a brand-new role).
    """
    role_id = str(role.get("id") or "")

    if role_id:
        for candidate in roles:
            if str(candidate.get("id")) == role_id:
                return MatchResult(role=candidate, kind=MatchKind.POSTING, score=1.0)
            if any(str(p.get("id")) == role_id for p in (candidate.get("postings") or [])):
                return MatchResult(role=candidate, kind=MatchKind.POSTING, score=1.0)

    key = identity_key(role)
    for candidate in roles:
        candidate_key = candidate.get("identity_key") or identity_key(candidate)
        if candidate_key == key:
            return MatchResult(role=candidate, kind=MatchKind.EXACT, score=1.0)

    company = norm_company(role.get("company"))
    best: Optional[MatchResult] = None
    for candidate in roles:
        if norm_company(candidate.get("company")) != company:
            continue
        score = title_similarity(role.get("title"), candidate.get("title"))
        if score >= STRONG:
            return MatchResult(role=candidate, kind=MatchKind.EXACT, score=score)
        if score >= threshold and (best is None or score > best.score):
            best = MatchResult(role=candidate, kind=MatchKind.NEAR, score=score)
    return best
