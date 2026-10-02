-- Skill match + published search rules: the dashboard's per-role "JD requirements vs
-- Richard's skills vs what his CV and LinkedIn actually show" table
-- (POST /api/dashboard/skill-match), and the read-only "Search rules" page the
-- job-search agent publishes (POST|GET /api/dashboard/rules).
-- Applied the same way as 001 (see that file's header). Idempotent and additive only.
--
-- APPLY THIS BEFORE DEPLOYING the backend that reads these columns: the mappers
-- write every column below on each insert/update (skill_match included), so the new
-- code fails against a database that does not have it yet.

alter table public.job_applications
    add column if not exists skill_match jsonb not null default '{}'::jsonb;

comment on column public.job_applications.skill_match is
    'JD requirements vs Richard''s experience vs what his CV and LinkedIn show, one row '
    'per requirement. Written only by POST /api/dashboard/skill-match (X-Ingest-Key), '
    'validated and summarised server-side (domain/applications/skill_match.py); '
    '{} means not analysed. Shape: {version, analyzed_on, verdict, cv_used, linkedin_used, '
    'jd_source: full_text|excerpt|null, rows: [{requirement, kind: must|nice, '
    'match: {level: strong|partial|gap, evidence}, '
    'cv: {level: shown|partial|missing|na, evidence, fix}, '
    'linkedin: {level: shown|partial|missing|na, evidence, fix}}], '
    'summary: {requirements, must, nice, match_*, cv_*, linkedin_*, to_surface}}. '
    'GET /applications returns it without rows; GET /applications/{id} returns it whole.';

create table if not exists public.job_search_rules (
    id smallint primary key default 1 check (id = 1),
    content jsonb not null,
    published_at timestamptz not null default now()
);

comment on table public.job_search_rules is
    'Singleton (id = 1): the rules document the job-search agent publishes with '
    'POST /api/dashboard/rules and the dashboard shows read-only on its Search rules '
    'page. content is opaque JSON that the API only sanity-checks (schema_version, '
    'lanes[].id/label/lines); the agent''s own config stays the source of truth. '
    'Republishing replaces the row.';

alter table public.job_search_rules enable row level security;
-- Deliberately no policies: only the service-role key (used server-side only) can read/write.
