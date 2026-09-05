"""One-off migration: profile/job-search/dashboard/roles-db.json -> Supabase.

Run manually, once:

    poetry run python scripts/migrate_dashboard_data.py

Reads SUPABASE_URL / SUPABASE_PROJECT_PASSWORD from .env (via python-dotenv-free
manual parsing, to avoid depending on the app's Settings wiring for a script that
runs outside the app). Idempotent: safe to re-run against an empty pair of tables,
but does not upsert -- clears both tables first so re-runs don't duplicate rows.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ROLES_DB_PATH = BACKEND_ROOT.parent / "profile" / "job-search" / "dashboard" / "roles-db.json"

EXTRAS_FIELDS = (
    "merged_from",
    "possible_duplicate_of",
    "status_previous",
    "cold_reason",
    "work_mode_previous",
    "jd_url_previous",
    "group_previous",
    "url_quality",
    "validated_account",
    "validated_at",
    "browser_surface",
)

FLAT_FIELDS = (
    "title", "company", "group", "score", "band", "status",
    "location_text", "work_mode", "employment_type", "salary_text",
    "posted_date", "posted_date_source", "posted_relative",
    "eligibility_text", "requirements_excerpt", "why_apply", "why_not",
    "considerations", "jd_url", "source", "found_by_query", "run_date",
    "first_seen", "last_seen", "live_state", "live_checked_at",
    "work_remote_allowed", "drop_stage", "drop_reason", "notes",
    "notes_updated_at",
)


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def build_conninfo(env: dict[str, str]) -> str:
    ref = re.match(r"https://([^.]+)\.supabase\.co", env["SUPABASE_URL"]).group(1)
    password = env.get("SUPABASE_PASSWORD") or env["SUPABASE_PROJECT_PASSWORD"]
    return (
        f"postgresql://postgres.{ref}:{password}"
        f"@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
    )


def to_row(role: dict) -> tuple:
    extras = {k: role[k] for k in EXTRAS_FIELDS if k in role}
    values = [role.get("id"), role.get("identity_key")]
    values += [role.get(f) for f in FLAT_FIELDS]
    values += [
        role.get("application_stage", "Not applied"),
        json.dumps(role.get("postings", [])),
        json.dumps(extras),
    ]
    return tuple(values)


def main() -> None:
    env = load_env(BACKEND_ROOT / ".env")
    conninfo = build_conninfo(env)
    data = json.loads(ROLES_DB_PATH.read_text(encoding="utf-8"))
    roles = data["roles"]
    runs = data["meta"]["runs"]

    dup_keys = [k for k, n in Counter(r.get("identity_key") for r in roles).items() if n > 1]
    missing_keys = [r.get("id") for r in roles if not r.get("identity_key")]
    if dup_keys or missing_keys:
        print("ABORTING - source data isn't clean enough to migrate as-is:")
        if dup_keys:
            print(f"  duplicate identity_key values: {dup_keys}")
        if missing_keys:
            print(f"  roles missing identity_key: {missing_keys}")
        raise SystemExit(1)

    source_histogram = Counter(r.get("status") for r in roles)
    print(f"source: {len(roles)} roles, {len(runs)} runs")
    print(f"source status histogram: {dict(source_histogram)}")

    insert_role_sql = f"""
        insert into public.job_applications (
            legacy_id, identity_key, {', '.join(f'"{f}"' for f in FLAT_FIELDS)},
            application_stage, postings, extras
        ) values (
            %s, %s, {', '.join(['%s'] * len(FLAT_FIELDS))}, %s, %s, %s
        )
    """
    insert_run_sql = """
        insert into public.job_search_runs (
            run_date, label, approx, searches_run, cards_surfaced, cards_opened,
            jd_extracted, card_screens, portals, notes, validated_account, browser_surface
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("truncate table public.job_applications, public.job_search_runs")
            cur.executemany(insert_role_sql, [to_row(r) for r in roles])
            cur.executemany(
                insert_run_sql,
                [
                    (
                        run.get("run_date"), run.get("label"), run.get("approx"),
                        run.get("searches_run"), run.get("cards_surfaced"),
                        run.get("cards_opened"), run.get("jd_extracted"),
                        json.dumps(run.get("card_screens", {})), run.get("portals"),
                        run.get("notes"), run.get("validated_account"),
                        run.get("browser_surface"),
                    )
                    for run in runs
                ],
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("select count(*) from public.job_applications")
            app_count = cur.fetchone()[0]
            cur.execute("select count(*) from public.job_search_runs")
            run_count = cur.fetchone()[0]
            cur.execute("select status, count(*) from public.job_applications group by status")
            db_histogram = dict(cur.fetchall())

    print(f"migrated: {app_count} applications, {run_count} runs")
    print(f"db status histogram: {db_histogram}")

    assert app_count == len(roles), f"application count mismatch: {app_count} != {len(roles)}"
    assert run_count == len(runs), f"run count mismatch: {run_count} != {len(runs)}"
    assert db_histogram == dict(source_histogram), "status histogram mismatch"
    print("OK - counts and histogram match source exactly")


if __name__ == "__main__":
    main()
