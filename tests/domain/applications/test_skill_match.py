"""normalize_skill_match: the stored shape, its defaults, trimming, the server-side
summary, and every way a payload can be wrong. Pure functions -- no I/O."""

import copy
from datetime import date, datetime, timezone

import pytest

from backend.domain.applications.skill_match import (
    MAX_EVIDENCE,
    MAX_FIX,
    MAX_REQUIREMENT,
    MAX_ROWS,
    MAX_VERDICT,
    normalize_skill_match,
)
from backend.domain.shared.errors import InvalidValueError
from tests.support.builders import skill_match_payload, skill_match_row

TODAY = date(2026, 10, 1)

DOCUMENTED_SUMMARY_KEYS = [
    "requirements", "must", "nice",
    "match_strong", "match_partial", "match_gap",
    "cv_shown", "cv_partial", "cv_missing",
    "linkedin_shown", "linkedin_partial", "linkedin_missing",
    "to_surface",
]


def one_row(**changes):
    """A payload with a single row whose keys are replaced by `changes`."""
    return {"rows": [{**skill_match_row(), **changes}]}


# -- shape and defaults -----------------------------------------------------------


def test_normalizes_a_full_payload_into_the_stored_shape():
    result = normalize_skill_match(skill_match_payload(), today=TODAY)

    assert list(result) == [
        "version", "analyzed_on", "verdict", "cv_used", "linkedin_used", "jd_source", "rows", "summary",
    ]
    assert result["version"] == 1
    assert result["analyzed_on"] == "2026-10-01"
    assert result["verdict"] == "Strong technical fit; LinkedIn does not show FastAPI yet."
    assert result["cv_used"] == "demo-cv.pdf"
    assert result["linkedin_used"] == "demo LinkedIn snapshot"
    assert result["jd_source"] == "full_text"
    assert result["rows"][0] == {
        "requirement": "Python, typed and tested; FastAPI",
        "kind": "must",
        "match": {"level": "strong", "evidence": "Evidence for: Python, typed and tested; FastAPI"},
        "cv": {"level": "shown", "evidence": None, "fix": None},
        "linkedin": {"level": "partial", "evidence": None, "fix": "Add FastAPI to the Skills list."},
    }
    assert [r["kind"] for r in result["rows"]] == ["must", "nice"]
    assert list(result["rows"][1]["match"]) == ["level", "evidence"]  # match carries no `fix`


def test_kind_defaults_to_must_when_missing_null_or_blank():
    rows = []
    for kind in ("<missing>", None, "", "  "):
        row = skill_match_row()
        if kind == "<missing>":
            del row["kind"]
        else:
            row["kind"] = kind
        rows.append(row)

    result = normalize_skill_match({"rows": rows}, today=TODAY)

    assert [r["kind"] for r in result["rows"]] == ["must"] * 4


def test_analyzed_on_defaults_to_today_when_missing_null_or_blank():
    for value in ("<missing>", None, "", "   "):
        raw = skill_match_payload()
        if value == "<missing>":
            del raw["analyzed_on"]
        else:
            raw["analyzed_on"] = value
        assert normalize_skill_match(raw, today=TODAY)["analyzed_on"] == "2026-10-01"


def test_analyzed_on_defaults_to_the_current_utc_date_when_no_clock_is_given():
    raw = skill_match_payload()
    del raw["analyzed_on"]

    before = datetime.now(tz=timezone.utc).date()
    stamped = normalize_skill_match(raw)["analyzed_on"]
    after = datetime.now(tz=timezone.utc).date()  # tolerate a midnight rollover mid-test

    assert stamped in {before.isoformat(), after.isoformat()}


def test_analyzed_on_accepts_an_iso_string_and_date_objects():
    assert normalize_skill_match(skill_match_payload(analyzed_on=" 2026-09-17 "))["analyzed_on"] == "2026-09-17"
    assert normalize_skill_match(skill_match_payload(analyzed_on=date(2026, 9, 18)))["analyzed_on"] == "2026-09-18"
    assert (
        normalize_skill_match(skill_match_payload(analyzed_on=datetime(2026, 9, 19, 12, 30)))["analyzed_on"]
        == "2026-09-19"
    )


def test_optional_header_fields_default_to_null():
    result = normalize_skill_match({"rows": [skill_match_row()]}, today=TODAY)

    assert (result["verdict"], result["cv_used"], result["linkedin_used"], result["jd_source"]) == (
        None, None, None, None,
    )


def test_jd_source_accepts_its_two_values_and_blank_means_null():
    assert normalize_skill_match(skill_match_payload(jd_source="excerpt"))["jd_source"] == "excerpt"
    assert normalize_skill_match(skill_match_payload(jd_source=None))["jd_source"] is None
    assert normalize_skill_match(skill_match_payload(jd_source="  "))["jd_source"] is None


# -- trimming, unknown keys, purity -----------------------------------------------


def test_strips_text_and_turns_empty_optional_text_into_null():
    row = skill_match_row("  Python  ")
    row["match"] = {"level": "strong", "evidence": "  six years  "}
    row["cv"] = {"level": "partial", "evidence": "   ", "fix": ""}
    row["linkedin"] = {"level": "missing", "evidence": None, "fix": "  Add it.  "}
    raw = skill_match_payload(rows=[row], verdict="   ", cv_used="", linkedin_used="  snapshot  ")

    result = normalize_skill_match(raw, today=TODAY)

    assert result["verdict"] is None
    assert result["cv_used"] is None
    assert result["linkedin_used"] == "snapshot"
    normalized = result["rows"][0]
    assert normalized["requirement"] == "Python"
    assert normalized["match"]["evidence"] == "six years"
    assert normalized["cv"] == {"level": "partial", "evidence": None, "fix": None}
    assert normalized["linkedin"] == {"level": "missing", "evidence": None, "fix": "Add it."}


def test_ignores_unknown_keys_and_never_trusts_a_summary_or_version_from_the_input():
    row = skill_match_row(linkedin="partial")
    row["extra"] = "ignored"
    row["match"]["extra"] = "ignored"
    row["cv"]["extra"] = "ignored"
    raw = skill_match_payload(
        rows=[row],
        summary={"requirements": 99, "to_surface": 99},
        version=7,
        surprise={"a": 1},
    )

    result = normalize_skill_match(raw, today=TODAY)

    assert set(result) == {
        "version", "analyzed_on", "verdict", "cv_used", "linkedin_used", "jd_source", "rows", "summary",
    }
    assert result["version"] == 1
    assert result["summary"]["requirements"] == 1
    assert result["summary"]["to_surface"] == 1
    assert set(result["rows"][0]) == {"requirement", "kind", "match", "cv", "linkedin"}
    assert set(result["rows"][0]["match"]) == {"level", "evidence"}
    assert set(result["rows"][0]["cv"]) == {"level", "evidence", "fix"}


def test_does_not_mutate_its_input():
    raw = skill_match_payload()
    snapshot = copy.deepcopy(raw)

    normalize_skill_match(raw, today=TODAY)

    assert raw == snapshot


def test_normalizing_its_own_output_changes_nothing():
    once = normalize_skill_match(skill_match_payload(), today=TODAY)

    assert normalize_skill_match(once, today=date(2030, 1, 1)) == once


# -- limits: exactly at the maximum is fine, one over is not -----------------------


def test_accepts_values_exactly_at_every_limit():
    row = skill_match_row("r" * MAX_REQUIREMENT)
    row["match"] = {"level": "strong", "evidence": "e" * MAX_EVIDENCE}
    row["cv"] = {"level": "partial", "evidence": "e" * MAX_EVIDENCE, "fix": "f" * MAX_FIX}
    raw = {"rows": [row] * MAX_ROWS, "verdict": "v" * MAX_VERDICT}

    result = normalize_skill_match(raw, today=TODAY)

    assert len(result["rows"]) == MAX_ROWS
    assert len(result["rows"][0]["requirement"]) == MAX_REQUIREMENT
    assert len(result["verdict"]) == MAX_VERDICT


# -- every way a payload can be wrong ---------------------------------------------

INVALID_PAYLOADS = [
    pytest.param(None, "skill_match must be an object", id="none"),
    pytest.param([], "skill_match must be an object", id="list"),
    pytest.param({}, "rows is required", id="empty-object"),
    pytest.param({"rows": None}, "rows is required", id="rows-null"),
    pytest.param({"rows": "text"}, "rows is required", id="rows-not-a-list"),
    pytest.param({"rows": []}, "rows is required", id="no-rows"),
    pytest.param(
        {"rows": [skill_match_row(f"requirement {i}") for i in range(MAX_ROWS + 1)]},
        "rows has 41 items, the maximum is 40",
        id="too-many-rows",
    ),
    pytest.param({"rows": ["text"]}, "rows[0] must be an object", id="row-not-an-object"),
    pytest.param(one_row(requirement=""), "rows[0].requirement must be 1 to 240 characters", id="empty-requirement"),
    pytest.param(one_row(requirement="   "), "rows[0].requirement must be 1 to 240", id="blank-requirement"),
    pytest.param(one_row(requirement=None), "rows[0].requirement must be 1 to 240", id="null-requirement"),
    pytest.param(one_row(requirement=42), "rows[0].requirement must be a string", id="requirement-not-a-string"),
    pytest.param(
        one_row(requirement="r" * (MAX_REQUIREMENT + 1)),
        "rows[0].requirement is 241 characters, the maximum is 240",
        id="requirement-too-long",
    ),
    pytest.param(one_row(kind="optional"), "rows[0].kind must be one of must, nice", id="unknown-kind"),
    pytest.param(one_row(kind="Must"), "rows[0].kind must be one of must, nice", id="kind-is-case-sensitive"),
    pytest.param(
        one_row(match={"level": "great", "evidence": "x"}),
        "rows[0].match.level must be one of strong, partial, gap (got 'great')",
        id="unknown-match-level",
    ),
    pytest.param(
        one_row(match={"level": "shown", "evidence": "x"}),
        "rows[0].match.level must be one of strong, partial, gap",
        id="coverage-level-on-match",
    ),
    pytest.param(
        one_row(match={"evidence": "x"}),
        "rows[0].match.level must be one of strong, partial, gap (got None)",
        id="match-level-missing",
    ),
    pytest.param(one_row(match=None), "rows[0].match is required", id="match-missing"),
    pytest.param(one_row(match="strong"), "rows[0].match is required", id="match-not-an-object"),
    pytest.param(
        one_row(match={"level": "strong"}),
        "rows[0].match.evidence is required",
        id="match-evidence-missing",
    ),
    pytest.param(
        one_row(match={"level": "strong", "evidence": "   "}),
        "rows[0].match.evidence is required",
        id="match-evidence-blank",
    ),
    pytest.param(
        one_row(match={"level": "strong", "evidence": "e" * (MAX_EVIDENCE + 1)}),
        "rows[0].match.evidence is 801 characters, the maximum is 800",
        id="match-evidence-too-long",
    ),
    pytest.param(
        one_row(cv={"level": "strong"}),
        "rows[0].cv.level must be one of shown, partial, missing, na (got 'strong')",
        id="unknown-cv-level",
    ),
    pytest.param(one_row(cv={}), "rows[0].cv.level must be one of shown, partial, missing, na", id="cv-level-missing"),
    pytest.param(one_row(cv=None), "rows[0].cv is required", id="cv-missing"),
    pytest.param(
        one_row(cv={"level": "shown", "evidence": "e" * (MAX_EVIDENCE + 1)}),
        "rows[0].cv.evidence is 801 characters, the maximum is 800",
        id="cv-evidence-too-long",
    ),
    pytest.param(
        one_row(cv={"level": "partial", "fix": "f" * (MAX_FIX + 1)}),
        "rows[0].cv.fix is 501 characters, the maximum is 500",
        id="cv-fix-too-long",
    ),
    pytest.param(
        one_row(cv={"level": "partial", "fix": 5}),
        "rows[0].cv.fix must be a string",
        id="cv-fix-not-a-string",
    ),
    pytest.param(
        one_row(linkedin={"level": "ok"}),
        "rows[0].linkedin.level must be one of shown, partial, missing, na (got 'ok')",
        id="unknown-linkedin-level",
    ),
    pytest.param(one_row(linkedin=None), "rows[0].linkedin is required", id="linkedin-missing"),
    pytest.param(
        one_row(linkedin={"level": "missing", "fix": "f" * (MAX_FIX + 1)}),
        "rows[0].linkedin.fix is 501 characters, the maximum is 500",
        id="linkedin-fix-too-long",
    ),
    pytest.param(
        skill_match_payload(verdict="v" * (MAX_VERDICT + 1)),
        "verdict is 601 characters, the maximum is 600",
        id="verdict-too-long",
    ),
    pytest.param(skill_match_payload(verdict=123), "verdict must be a string", id="verdict-not-a-string"),
    pytest.param(
        skill_match_payload(cv_used="c" * 601),
        "cv_used is 601 characters, the maximum is 600",
        id="cv-used-too-long",
    ),
    pytest.param(
        skill_match_payload(linkedin_used=["a"]),
        "linkedin_used must be a string",
        id="linkedin-used-not-a-string",
    ),
    pytest.param(
        skill_match_payload(jd_source="pdf"),
        "jd_source must be one of full_text, excerpt (got 'pdf')",
        id="unknown-jd-source",
    ),
    pytest.param(skill_match_payload(analyzed_on="yesterday"), "analyzed_on must be an ISO date", id="date-word"),
    pytest.param(skill_match_payload(analyzed_on="2026-13-45"), "analyzed_on must be an ISO date", id="date-nonsense"),
    pytest.param(skill_match_payload(analyzed_on="01/10/2026"), "analyzed_on must be an ISO date", id="date-slashes"),
    pytest.param(
        skill_match_payload(analyzed_on="2026-10-01T10:00:00"),
        "analyzed_on must be an ISO date",
        id="date-with-time",
    ),
    pytest.param(skill_match_payload(analyzed_on=20261001), "analyzed_on must be an ISO date", id="date-number"),
]


@pytest.mark.parametrize(("raw", "message"), INVALID_PAYLOADS)
def test_rejects_an_invalid_payload_and_names_the_problem(raw, message):
    with pytest.raises(InvalidValueError) as caught:
        normalize_skill_match(raw, today=TODAY)

    assert message in str(caught.value)


def test_names_the_row_that_is_wrong():
    rows = [skill_match_row("fine"), skill_match_row("also fine"), {**skill_match_row("broken"), "cv": {"level": "x"}}]

    with pytest.raises(InvalidValueError, match=r"rows\[2\]\.cv\.level"):
        normalize_skill_match({"rows": rows}, today=TODAY)


# -- summary ----------------------------------------------------------------------


def _summary_rows():
    return [
        skill_match_row("r1", match="strong", cv="shown", linkedin="shown"),
        skill_match_row("r2", match="strong", cv="partial", linkedin="shown"),
        skill_match_row("r3", match="partial", cv="shown", linkedin="missing"),
        skill_match_row("r4", kind="nice", match="partial", cv="missing", linkedin="missing"),
        skill_match_row("r5", match="gap", cv="missing", linkedin="missing"),
        skill_match_row("r6", kind="nice", match="gap", cv="na", linkedin="na"),
        skill_match_row("r7", match="strong", cv="na", linkedin="partial"),
        skill_match_row("r8", match="strong", cv="na", linkedin="na"),
    ]


def test_summary_counts_every_bucket_and_leaves_na_out_of_the_coverage_buckets():
    summary = normalize_skill_match({"rows": _summary_rows()}, today=TODAY)["summary"]

    assert summary == {
        "requirements": 8,
        "must": 6,
        "nice": 2,
        "match_strong": 4,   # r1 r2 r7 r8
        "match_partial": 2,  # r3 r4
        "match_gap": 2,      # r5 r6
        "cv_shown": 2,       # r1 r3
        "cv_partial": 1,     # r2
        "cv_missing": 2,     # r4 r5   (r6 r7 r8 are na: in no cv bucket)
        "linkedin_shown": 2,    # r1 r2
        "linkedin_partial": 1,  # r7
        "linkedin_missing": 3,  # r3 r4 r5   (r6 r8 are na)
        "to_surface": 4,     # r2 r3 r4 r7
    }


def test_summary_has_exactly_the_documented_keys_in_order():
    summary = normalize_skill_match({"rows": _summary_rows()}, today=TODAY)["summary"]

    assert list(summary) == DOCUMENTED_SUMMARY_KEYS


def test_summary_buckets_add_up_to_the_row_count():
    summary = normalize_skill_match({"rows": _summary_rows()}, today=TODAY)["summary"]

    assert summary["must"] + summary["nice"] == summary["requirements"]
    assert summary["match_strong"] + summary["match_partial"] + summary["match_gap"] == summary["requirements"]
    na_cv = 3  # r6 r7 r8
    assert summary["cv_shown"] + summary["cv_partial"] + summary["cv_missing"] == summary["requirements"] - na_cv


@pytest.mark.parametrize(
    ("match", "cv", "linkedin", "surfaces"),
    [
        ("strong", "shown", "shown", False),
        ("strong", "partial", "shown", True),
        ("strong", "shown", "partial", True),
        ("strong", "missing", "shown", True),
        ("strong", "shown", "missing", True),
        ("partial", "missing", "missing", True),
        ("partial", "shown", "shown", False),
        ("gap", "missing", "missing", False),
        ("gap", "partial", "partial", False),
        ("strong", "na", "na", False),
        ("strong", "na", "partial", True),
        ("partial", "missing", "na", True),
    ],
)
def test_to_surface_needs_a_matched_requirement_that_a_document_shows_badly(match, cv, linkedin, surfaces):
    row = skill_match_row(match=match, cv=cv, linkedin=linkedin)

    summary = normalize_skill_match({"rows": [row]}, today=TODAY)["summary"]

    assert summary["to_surface"] == (1 if surfaces else 0)
