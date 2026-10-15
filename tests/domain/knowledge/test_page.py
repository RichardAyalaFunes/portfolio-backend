"""The rules a published document must meet. The body is rendered by the dashboard as React
components, so what these tests pin is what keeps a hostile or malformed document from reaching it."""

import pytest

from backend.domain.knowledge.page import KnowledgePage
from backend.domain.shared.errors import InvalidValueError
from tests.support.knowledge_builders import make_document, text_block


def body(*blocks):
    return {"blocks": list(blocks), "outline": [], "related": []}


def test_a_valid_document_becomes_a_page_with_every_field_carried():
    page = KnowledgePage.from_document(make_document(links=["reference/backend/dead-letter-queue"]))

    assert page.slug == "reference/backend/idempotency"
    assert page.space == "reference"
    assert page.kind == "concept"
    assert page.title == "Idempotency"
    assert page.group == "Backend"
    assert page.read_minutes == 3
    assert page.tags == ("reliability", "retries")
    assert page.aliases == ("idempotency key", "idempotent")
    assert page.links == ("reference/backend/dead-letter-queue",)
    assert page.source_updated == "2026-09-30"
    assert "Retries happen" in page.search_text
    assert page.body["blocks"][0]["t"] == "callout"


@pytest.mark.parametrize(
    "slug",
    ["", "idempotency", "other/backend/idempotency", "reference/Backend/Idempotency", "reference/", "reference/a b", "../reference/x"],
)
def test_a_slug_outside_the_three_spaces_or_not_kebab_case_is_rejected(slug):
    with pytest.raises(InvalidValueError, match="slug"):
        KnowledgePage.from_document(make_document(slug) if slug else {"slug": slug})


def test_the_space_must_match_the_slug_prefix():
    with pytest.raises(InvalidValueError, match="space"):
        KnowledgePage.from_document(make_document(space="learn"))


def test_an_unknown_kind_is_rejected():
    with pytest.raises(InvalidValueError, match="kind"):
        KnowledgePage.from_document(make_document(kind="essay"))


@pytest.mark.parametrize("field", ["title"])
def test_a_missing_title_is_rejected(field):
    with pytest.raises(InvalidValueError, match=field):
        KnowledgePage.from_document(make_document(**{field: "  "}))


def test_the_error_names_the_page():
    with pytest.raises(InvalidValueError, match=r"^reference/backend/idempotency: kind"):
        KnowledgePage.from_document(make_document(kind="essay"))


def test_an_unknown_block_type_is_rejected():
    with pytest.raises(InvalidValueError, match="unknown block"):
        KnowledgePage.from_document(make_document(body=body({"t": "script", "src": "x"})))


def test_an_unknown_inline_node_is_rejected():
    with pytest.raises(InvalidValueError, match="unknown inline"):
        KnowledgePage.from_document(make_document(body=body({"t": "p", "c": [{"t": "html", "v": "<script>"}]})))


@pytest.mark.parametrize("href", ["javascript:alert(1)", "data:text/html;base64,AAAA", "//evil.example", "/relative"])
def test_a_link_must_be_http_or_mailto(href):
    block = {"t": "p", "c": [{"t": "a", "href": href, "c": ["x"]}]}
    with pytest.raises(InvalidValueError, match="http"):
        KnowledgePage.from_document(make_document(body=body(block)))


def test_an_https_link_and_an_internal_reference_are_accepted():
    block = {
        "t": "p",
        "c": [
            {"t": "a", "href": "https://nextjs.org/docs", "c": ["docs"]},
            {"t": "ref", "slug": "reference/frontend/hydration", "auto": True, "c": ["hydration"]},
            {"t": "missing", "name": "Postgres", "c": ["Postgres"]},
        ],
    }
    page = KnowledgePage.from_document(make_document(body=body(block)))
    assert page.body["blocks"][0]["c"][1]["slug"] == "reference/frontend/hydration"


def test_a_reference_needs_a_valid_slug():
    block = {"t": "p", "c": [{"t": "ref", "slug": "http://evil.example", "c": ["x"]}]}
    with pytest.raises(InvalidValueError, match="reference"):
        KnowledgePage.from_document(make_document(body=body(block)))


def test_nesting_deeper_than_the_limit_is_rejected():
    node = text_block("deep")
    for _ in range(12):
        node = {"t": "quote", "c": [node]}
    with pytest.raises(InvalidValueError, match="deeper"):
        KnowledgePage.from_document(make_document(body=body(node)))


def test_a_body_over_the_size_limit_is_rejected():
    huge = {"t": "code", "lang": "", "text": "x" * 700_000}
    with pytest.raises(InvalidValueError, match="bytes"):
        KnowledgePage.from_document(make_document(body=body(huge)))


def test_a_non_finite_number_in_the_body_is_rejected():
    bad = {"t": "diagram", "kind": "flow", "w": float("nan"), "h": 10, "nodes": [], "edges": []}
    with pytest.raises(InvalidValueError, match="plain JSON"):
        KnowledgePage.from_document(make_document(body=body(bad)))


def test_a_flow_diagram_needs_positioned_nodes_and_edges_with_points():
    good = {
        "t": "diagram",
        "kind": "flow",
        "dir": "TD",
        "w": 200,
        "h": 120,
        "nodes": [{"id": "A", "x": 10, "y": 10, "w": 80, "h": 38, "lines": ["Start"], "shape": "rect"}],
        "edges": [{"pts": [[50, 48], [50, 90]], "label": None, "style": "solid", "arrow": True, "back": False}],
    }
    KnowledgePage.from_document(make_document(body=body(good)))

    broken = {**good, "edges": [{"pts": [[50, 48]]}]}
    with pytest.raises(InvalidValueError, match="two"):
        KnowledgePage.from_document(make_document(body=body(broken)))


def test_a_table_marks_column_must_exist():
    table = {"t": "table", "head": [["#"], ["Question"], ["Mark"]], "align": [], "rows": [], "marks": 5}
    with pytest.raises(InvalidValueError, match="marks"):
        KnowledgePage.from_document(make_document(body=body(table)))


def test_links_must_be_valid_slugs_and_tags_must_be_strings():
    with pytest.raises(InvalidValueError, match="links"):
        KnowledgePage.from_document(make_document(links=["not a slug"]))
    with pytest.raises(InvalidValueError, match="tags"):
        KnowledgePage.from_document(make_document(tags=[1, 2]))


def test_the_source_date_must_be_an_iso_date():
    with pytest.raises(InvalidValueError, match="source_updated"):
        KnowledgePage.from_document(make_document(source_updated="last Tuesday"))
