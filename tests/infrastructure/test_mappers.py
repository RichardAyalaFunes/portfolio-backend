"""Supabase row <-> JobApplication mapping. The mappers write every column on each
insert/update, so a field they forget to carry is silently lost on the next save."""

import dataclasses
import json

from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.skill_match import normalize_skill_match
from backend.infrastructure.adapters.driven.supabase.mappers import entity_to_row, row_to_entity
from tests.support.builders import make_application, skill_match_payload


def test_skill_match_survives_entity_to_row_and_back():
    payload = normalize_skill_match(skill_match_payload())
    application = make_application(skill_match=payload)

    row = entity_to_row(application)
    assert row["skill_match"] == payload

    # What PostgREST hands back is parsed JSON, so push the row through a real encode/decode.
    restored = row_to_entity(json.loads(json.dumps(row)))
    assert restored.skill_match == payload
    assert restored == application  # JobApplication is a dataclass: a field-by-field comparison


def test_a_new_application_writes_an_empty_skill_match():
    assert entity_to_row(make_application())["skill_match"] == {}


def test_rows_without_the_column_or_with_null_read_as_an_empty_skill_match():
    row = entity_to_row(make_application())

    del row["skill_match"]
    assert row_to_entity(row).skill_match == {}

    row["skill_match"] = None
    assert row_to_entity(row).skill_match == {}


def test_every_aggregate_field_is_written_to_the_row():
    """Guards the next column someone adds to JobApplication and forgets in the mapper."""
    row = entity_to_row(make_application())
    fields = {f.name for f in dataclasses.fields(JobApplication) if not f.name.startswith("_")}

    assert fields - set(row) == set()
    assert "skill_match" in fields
