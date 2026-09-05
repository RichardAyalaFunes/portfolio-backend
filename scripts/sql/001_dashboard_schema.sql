-- Job Applications Dashboard schema.
-- Applied directly via psycopg (see scripts/migrate_dashboard_data.py) because this
-- project isn't reachable through the connected Supabase MCP tool. Safe to re-run:
-- every statement is idempotent (IF NOT EXISTS / CREATE OR REPLACE).

create table if not exists public.job_applications (
    id uuid primary key default gen_random_uuid(),
    legacy_id text,
    identity_key text not null unique,
    title text not null,
    company text not null,
    "group" text,
    score integer,
    band text,
    status text not null check (status in ('To validate', 'Approved', 'Rejected', 'Cold', 'Flagged', 'Dropped')),
    application_stage text not null default 'Not applied'
        check (application_stage in ('Not applied', 'Applied', 'Interviewing', 'Offer', 'Closed')),
    location_text text,
    work_mode text,
    employment_type text,
    salary_text text,
    posted_date date,
    posted_date_source text,
    posted_relative text,
    eligibility_text text,
    requirements_excerpt text,
    why_apply text,
    why_not text,
    considerations text,
    jd_url text,
    source text,
    found_by_query text,
    run_date date,
    first_seen date,
    last_seen date,
    live_state text,
    live_checked_at date,
    work_remote_allowed boolean,
    drop_stage text,
    drop_reason text,
    notes text not null default '',
    notes_updated_at date,
    postings jsonb not null default '[]'::jsonb,
    extras jsonb not null default '{}'::jsonb,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_job_applications_status on public.job_applications (status);
create index if not exists idx_job_applications_stage on public.job_applications (application_stage);
create index if not exists idx_job_applications_posted_date on public.job_applications (posted_date desc);
create index if not exists idx_job_applications_run_date on public.job_applications (run_date);
create index if not exists idx_job_applications_archived_at on public.job_applications (archived_at);

create table if not exists public.job_search_runs (
    run_date date primary key,
    label text,
    approx boolean,
    searches_run integer,
    cards_surfaced integer,
    cards_opened integer,
    jd_extracted integer,
    card_screens jsonb not null default '{}'::jsonb,
    portals text[],
    notes text,
    validated_account text,
    browser_surface text
);

create table if not exists public.dashboard_login_attempts (
    id bigint generated always as identity primary key,
    ip inet,
    device_id text,
    success boolean not null,
    attempted_at timestamptz not null default now()
);

create index if not exists idx_login_attempts_ip_time on public.dashboard_login_attempts (ip, attempted_at);
create index if not exists idx_login_attempts_device_time on public.dashboard_login_attempts (device_id, attempted_at);

alter table public.job_applications enable row level security;
alter table public.job_search_runs enable row level security;
alter table public.dashboard_login_attempts enable row level security;
-- Deliberately no policies: only the service-role key (used server-side only) can read/write.

-- keep updated_at honest on every UPDATE
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_job_applications_updated_at on public.job_applications;
create trigger trg_job_applications_updated_at
    before update on public.job_applications
    for each row execute function public.set_updated_at();
