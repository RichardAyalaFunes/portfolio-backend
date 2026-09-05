"""
Parity tests for domain.applications.identity against real rows from
profile/job-search/dashboard/roles-db.json, pinning down both the intended
behavior and the two known quirks documented in identity.py's module docstring.
"""

from backend.domain.applications.identity import (
    MatchKind,
    find_match,
    identity_key,
    norm_company,
    norm_title,
    title_similarity,
)


def test_deel_repost_folds_via_title_similarity_not_key_equality():
    """A real repost (roles-db.json id 4455897465, merged_from 4454666106): the
    reposted title gained a 'Sr.' prefix and a '(Remote)' suffix, so the two
    identity_key strings differ -- tier 2 (exact key match) must NOT catch this.
    It only folds because MEANINGLESS drops 'engineer'/'ai'/'senior', leaving
    {backend, growth} on both sides for a perfect Jaccard match."""
    original = {"id": "4454666106", "company": "Deel", "title": "Backend Engineer, AI | Growth"}
    repost = {"id": "4455897465", "company": "Deel", "title": "Sr. Backend Engineer, AI | Growth (Remote)"}

    assert identity_key(original) != identity_key(repost)
    assert title_similarity(original["title"], repost["title"]) == 1.0

    match = find_match(repost, [original])
    assert match is not None
    assert match.kind == MatchKind.EXACT
    assert match.role is original


def test_cit_specialist_and_master_stay_separate():
    """Two real, distinct CI&T roles must NOT be flagged as related at all --
    not even as a 'near' hit for human review."""
    specialist = {"id": "4454532283", "company": "CI&T", "title": "AI Engineer Specialist, Brazil"}
    master = {"id": "4456777089", "company": "CI&T", "title": "AI Engineer Master, Brazil"}

    assert norm_company("CI&T") == "ci t"
    assert title_similarity(specialist["title"], master["title"]) == 0.0
    assert find_match(master, [specialist]) is None


def test_qubika_dotted_sa_suffix_does_not_fold_known_gap():
    """Documented quirk: 'S.A.' (dotted) splits into two single-letter tokens
    that COMPANY_NOISE doesn't cover, unlike the undotted 'SA' form."""
    assert norm_company("Qubika") == "qubika"
    assert norm_company("Qubika Careers") == "qubika"
    assert norm_company("Qubika SA") == "qubika"
    assert norm_company("Qubika S.A.") == "qubika s a"


def test_fde_synonym_can_duplicate_words_known_quirk():
    """Documented quirk: a title that already spells out the phrase next to the
    abbreviation gets it twice, because the synonym expansion isn't skipped
    when the expansion's words are already present. Matches the real migrated
    row (identity_key 'qubika::forward deployed engineer forward deployed engineer')."""
    assert norm_title("Forward Deployed Engineer (FDE)") == "forward deployed engineer forward deployed engineer"


def test_posting_id_match_beats_identity_key_beats_title_similarity():
    """The three tiers must be tried in order -- a posting-id hit anywhere in
    the list wins even if a later candidate would also match by identity_key."""
    by_posting = {"id": "111", "company": "Acme", "title": "Old Title", "postings": [{"id": "999"}]}
    by_key = {"id": "222", "company": "Acme", "title": "New Role", "identity_key": "acme::new incoming role"}
    incoming = {"id": "999", "company": "Acme", "title": "New Incoming Role"}

    match = find_match(incoming, [by_key, by_posting])
    assert match is not None
    assert match.kind == MatchKind.POSTING
    assert match.role is by_posting


def test_near_hit_tracks_best_score_not_first_hit():
    incoming = {"company": "Acme", "title": "Senior Backend Platform Engineer"}
    # tokens {backend, platform} vs {backend, support} -> 1/3
    weaker = {"id": "1", "company": "Acme", "title": "Backend Support Engineer"}
    # tokens {backend, platform} vs {backend, platform, growth} -> 2/3
    stronger = {"id": "2", "company": "Acme", "title": "Backend Platform Growth Engineer"}
    assert title_similarity(incoming["title"], weaker["title"]) < title_similarity(incoming["title"], stronger["title"])

    match = find_match(incoming, [weaker, stronger], threshold=0.1)
    assert match is not None
    assert match.kind == MatchKind.NEAR
    assert match.role is stronger


def test_no_match_returns_none():
    incoming = {"company": "Brand New Co", "title": "Something Nobody Has Posted"}
    assert find_match(incoming, [{"company": "Other Co", "title": "Unrelated Title"}]) is None
