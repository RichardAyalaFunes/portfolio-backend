-- Knowledge library: the AI-written notes of the Obsidian vault (_AI_Coach, _AI_Knowledge,
-- _AI_Evaluations) published as pages for the dashboard's /dashboard/knowledge section.
-- Written by the vault publisher (.claude/skills/ai-coach/scripts/knowledge/publish-knowledge.js in
-- the operating-layer repo) through POST /api/dashboard/knowledge/pages (X-Ingest-Key), read by the
-- dashboard through GET /api/dashboard/knowledge* (Bearer device token).
--
-- Applied the same way as 001 (see that file's header). Idempotent and additive only: it creates
-- one new table and touches nothing that exists. The new endpoints return an error until it is
-- applied; every existing endpoint is unaffected either way.

create table if not exists public.knowledge_pages (
    slug text primary key,
    space text not null check (space in ('learn', 'reference', 'practice')),
    kind text not null,
    title text not null,
    group_label text not null default '',
    group_order integer not null default 0,
    sort_order integer not null default 0,
    domain text,
    summary text not null default '',
    read_minutes integer not null default 1 check (read_minutes between 1 and 240),
    tags text[] not null default '{}',
    aliases text[] not null default '{}',
    links text[] not null default '{}',
    source_path text,
    source_updated date,
    content_hash text,
    body jsonb not null,
    search_text text not null default '',
    published_at timestamptz not null default now()
);

comment on table public.knowledge_pages is
    'One row per published note. slug = <space>/<folders>/<note>, kebab-cased. body is block-and-inline '
    'JSON rendered by React components (never injected as HTML); the shape is validated server-side by '
    'domain/knowledge/page.py and documented in docs/knowledge-library.md. links = outgoing page slugs '
    '(written by the note, plus inferred term links); backlinks are computed from it at read time. '
    'search_text is the plain text the word-start search runs over. Republishing a slug replaces it.';

create index if not exists knowledge_pages_order_idx
    on public.knowledge_pages (space, group_order, group_label, sort_order, title);

create index if not exists knowledge_pages_links_idx
    on public.knowledge_pages using gin (links);

alter table public.knowledge_pages enable row level security;
-- Deliberately no policies: only the service-role key (used server-side only) can read/write.
