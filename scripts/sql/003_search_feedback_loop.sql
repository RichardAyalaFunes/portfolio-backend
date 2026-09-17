-- Search feedback loop: lets the job-search agent read Richard's latest review
-- decisions (GET /api/dashboard/feedback) and record what it changed in its own
-- search plan, so each run improves on the last one.
-- Applied the same way as 001 (see that file's header). Idempotent.
--
-- APPLY THIS BEFORE DEPLOYING the backend that reads these columns: the mappers
-- write every column below on each insert/update.

alter table public.job_applications
    add column if not exists reviewed_at timestamptz,
    add column if not exists secondary_lanes jsonb not null default '[]'::jsonb,
    add column if not exists discovery_queries jsonb not null default '[]'::jsonb,
    add column if not exists tags jsonb not null default '[]'::jsonb;

comment on column public.job_applications.reviewed_at is
    'When Richard last gave feedback on this role: set whenever the dashboard (Bearer '
    'PATCH) changes status, stage or notes, or annotate.js attaches a review comment. '
    'Never set by ingest. GET /feedback reads rows with reviewed_at >= since.';
comment on column public.job_applications.secondary_lanes is
    'Other interest groups the role also satisfies. The primary lane stays in "group".';
comment on column public.job_applications.discovery_queries is
    'Every search line (keywords + anchor) that surfaced this role, unioned across runs. '
    'Drives the per-line yield that decides which search strings earn their slot.';
comment on column public.job_applications.tags is
    'Review warnings the agent attaches so Richard checks the right thing first, e.g. '
    'location_unsure, big_corporate, salary_unknown, language_mixed, '
    'company_type_unclear. Replaced wholesale by the latest run that reports the role.';

-- Existing review comments count as feedback too.
update public.job_applications
   set reviewed_at = notes_updated_at::timestamptz
 where reviewed_at is null
   and notes_updated_at is not null
   and coalesce(notes, '') <> '';

create index if not exists idx_job_applications_reviewed_at on public.job_applications (reviewed_at desc);

alter table public.job_search_runs
    add column if not exists outcome jsonb not null default '{}'::jsonb,
    add column if not exists line_yield jsonb not null default '[]'::jsonb,
    add column if not exists plan_changes jsonb not null default '[]'::jsonb;

comment on column public.job_search_runs.outcome is
    'Run result counts: {passed, flagged, borderline, dropped, jds_read, target_met}.';
comment on column public.job_search_runs.line_yield is
    'Per search line: [{line, portal, surfaced, new_after_dedupe, read, passed, flagged}].';
comment on column public.job_search_runs.plan_changes is
    'What the agent changed in its adaptive search plan this run, and why: '
    '[{action: add|retire|promote|rewrite|propose_gate_change, line, reason, evidence}].';
