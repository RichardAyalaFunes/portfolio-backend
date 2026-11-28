"""Search traceability: summing every run's line_yield per search (line + portal)."""

from backend.application.applications.get_search_stats.handler import search_stats, technique_of


def run(date, *entries):
    return {"run_date": date, "line_yield": list(entries)}


def entry(line, portal="linkedin", **counts):
    return {"line": line, "portal": portal, **counts}


def test_a_search_is_summed_across_runs_and_repeats_count():
    runs = [
        run("2026-11-01", entry('"ai engineer" @peru', surfaced=40, new_after_dedupe=10, read=10, passed=1)),
        run("2026-11-05", entry('"ai engineer" @peru', surfaced=30, new_after_dedupe=5, read=5, passed=2, flagged=1)),
    ]
    stats = search_stats(runs, {'"ai engineer" @peru': {"surfaced": 7, "approved": 2, "applied": 1}})
    (row,) = stats["searches"]
    assert (row["executions"], row["surfaced"], row["new"], row["passed"], row["flagged"]) == (2, 70, 15, 3, 1)
    assert (row["roles"], row["approved"], row["applied"]) == (7, 2, 1)
    assert (row["first_run"], row["last_run"]) == ("2026-11-01", "2026-11-05")
    assert [h["run_date"] for h in row["history"]] == ["2026-11-01", "2026-11-05"]
    assert row["pass_rate"] == 0.2
    assert stats["totals"]["executions"] == 2 and stats["totals"]["runs"] == 2


def test_the_same_line_on_two_portals_is_two_searches():
    stats = search_stats([run("2026-11-01", entry("ai engineer", "linkedin", surfaced=5), entry("ai engineer", "wellfound", surfaced=3))], {})
    assert {(r["portal"], r["surfaced"]) for r in stats["searches"]} == {("linkedin", 5), ("wellfound", 3)}
    assert stats["by_portal"]["wellfound"]["surfaced"] == 3


def test_techniques_are_stated_or_inferred():
    assert technique_of({"line": "x", "technique": "alert"}) == "alert"
    assert technique_of({"line": "linkedin_section: top picks", "portal": "linkedin"}) == "section"
    assert technique_of({"line": '"ai engineer" @peru', "portal": "linkedin"}) == "search_string"
    assert technique_of({"line": "jobs board, remote filter", "portal": "ycombinator"}) == "board"
    assert technique_of({"line": "2-day harvest (unattributed)", "portal": "linkedin"}) == "other"


def test_bad_or_missing_counts_never_break_the_sum():
    stats = search_stats([run("2026-11-01", entry("a", surfaced=None, passed="2", new_after_dedupe=-1)), {"run_date": "2026-11-02"}], {})
    (row,) = stats["searches"]
    assert (row["surfaced"], row["passed"], row["new"]) == (0, 0, 0)
    assert stats["totals"]["runs"] == 1
