-- Role enrichment: outreach contacts + application-form intel for high-score roles.
-- Applied the same way as 001 (see that file's header). Idempotent.
--
-- Both columns are intentionally schemaless JSON, not normalized tables --
-- Richard's own instruction: "questions are dynamic... don't need to complicate
-- stuff", and the same reasoning applies to a contact record (its shape depends
-- on the source: LinkedIn people search vs. a role's own network block vs. a
-- YC team page). The API layer documents the shape it writes/reads; nothing in
-- the DB enforces it.

alter table public.job_applications
    add column if not exists contacts jsonb not null default '[]'::jsonb,
    add column if not exists application_form jsonb not null default '{}'::jsonb;

comment on column public.job_applications.contacts is
    'Ordered array of outreach candidates for this role (recruiters, hiring managers, '
    'founders...), written by the enrich.js CLI script for roles scoring >=80. Each '
    'item: {id, name, title, linkedin_url, linkedin_slug, connection_degree, '
    'mutual_connections, category, priority_rank, reason, message_draft, outreach_stage, '
    'outreach_stage_updated_at, source, found_at}. outreach_stage is the one field '
    'Richard updates from the dashboard after he sends a message by hand -- the agent '
    'never re-sends or re-ranks once it exists.';

comment on column public.job_applications.application_form is
    'What the enrichment step found at the role''s real apply destination (never '
    'LinkedIn Easy Apply -- skipped by policy). Shape: {apply_type, apply_url, '
    'checked_at, skipped_reason, questions: [{question, required, field_type, '
    'classification: trivial|substantive, answer_bullets, answer_draft}]}. Draft-only, '
    'always -- nothing here is ever submitted by the agent.';
