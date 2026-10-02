"""The small questions the dashboard asks of a role: has it been applied to, is its posting
dead, did it score under the bar, is it waiting for Richard's first look. The last one is
the rule behind the queue's "To review" bucket (frontend queueBuckets.ts), and the metrics
and rules counters share it, so it is pinned here case by case."""

import pytest

from backend.domain.applications.value_objects import APPLIED_STAGES, DEAD_POSTING_STATES, Stage, Status
from tests.support.builders import make_application


@pytest.mark.parametrize("stage", list(Stage))
def test_has_applied_is_every_stage_after_not_applied_the_closed_end_included(stage):
    application = make_application(application_stage=stage)

    assert application.has_applied is (stage != Stage.NOT_APPLIED)
    assert (stage in APPLIED_STAGES) is application.has_applied


@pytest.mark.parametrize(
    ("live_state", "dead"),
    [
        ("CLOSED", True),
        ("SUSPENDED", True),
        ("GONE", True),
        ("LISTED", False),
        ("UNVERIFIABLE", False),  # the sweep could not tell: treated as open
        (None, False),  # never checked
    ],
)
def test_a_posting_is_dead_only_when_the_sweep_said_closed_suspended_or_gone(live_state, dead):
    assert make_application(live_state=live_state).posting_is_dead is dead
    assert (live_state in DEAD_POSTING_STATES) is dead


@pytest.mark.parametrize(
    ("overrides", "below"),
    [
        ({"drop_stage": "scored"}, True),
        ({"drop_reason": "below_bar"}, True),
        ({"drop_stage": "scored", "drop_reason": "below_bar"}, True),
        ({"drop_stage": "read", "drop_reason": "off_lane"}, False),  # cut by a gate, never scored
        ({}, False),
    ],
)
def test_below_bar_means_the_agent_scored_it_and_it_fell_short(overrides, below):
    assert make_application(**overrides).is_below_bar is below


@pytest.mark.parametrize(
    ("overrides", "waiting"),
    [
        # The one that counts: no verdict, not applied, open (or unchecked), not under the bar.
        ({}, True),
        ({"live_state": "LISTED"}, True),
        ({"live_state": "UNVERIFIABLE"}, True),
        # Anything else leaves To review.
        ({"live_state": "CLOSED"}, False),
        ({"live_state": "SUSPENDED"}, False),
        ({"live_state": "GONE"}, False),
        ({"drop_stage": "scored", "drop_reason": "below_bar"}, False),
        ({"application_stage": Stage.APPLIED}, False),
        ({"application_stage": Stage.INTERVIEWING}, False),
        ({"application_stage": Stage.OFFER}, False),
        ({"application_stage": Stage.CLOSED}, False),
        ({"status": Status.APPROVED}, False),
        ({"status": Status.REJECTED}, False),
        ({"status": Status.COLD}, False),
        ({"status": Status.FLAGGED}, False),
        ({"status": Status.DROPPED}, False),
    ],
)
def test_awaits_review_is_a_role_nobody_has_decided_on_that_is_still_open_and_passed_the_bar(overrides, waiting):
    assert make_application(**overrides).awaits_review is waiting
