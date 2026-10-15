# Knowledge library

The dashboard's `/dashboard/knowledge` section: the AI-written notes of Richard's Obsidian vault
(`_AI_Coach`, `_AI_Knowledge`, `_AI_Evaluations`) published as cross-linked, searchable pages.
Private: reads need the dashboard's device token, like every other `/api/dashboard` route.

## Flow

```
Obsidian vault (H:)  --publish-knowledge.js-->  POST /api/dashboard/knowledge/pages  --> knowledge_pages (Supabase)
                                                                                              |
dashboard /dashboard/knowledge  <--  GET /api/dashboard/knowledge | /search | /pages/{slug}  <--+
```

The publisher lives in the operating-layer repo at
`.claude/skills/ai-coach/scripts/knowledge/` (Node, no dependencies, tests with `node --test`). It
reads the vault, converts each note to a document below, resolves links and posts batches. Notes are
never edited, and Richard's own Title Case notes are never read.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/dashboard/knowledge` | Bearer | Every page as a summary row (no body), in library order |
| GET | `/api/dashboard/knowledge/search?q=` | Bearer | Word-start search over all text; ranked, with a snippet |
| GET | `/api/dashboard/knowledge/pages/{slug}` | Bearer | One page: body, outgoing links, and backlinks computed at read time |
| POST | `/api/dashboard/knowledge/pages` | `X-Ingest-Key` | Upsert a batch (at most 60 pages). One invalid page rejects the batch with a 422 naming it |
| POST | `/api/dashboard/knowledge/prune` | `X-Ingest-Key` | `{keep: [slugs]}`: remove stored pages not in the list. Refuses an empty list and any list that would remove more than half of a library of 10 or more |

Search semantics: every term must match the start of a word, case-insensitively (`idemp` finds
`idempotency`, `race` finds `race condition` and not `trace`). Ranking: all terms in the title, then a
term in an alias, then in a tag, then body occurrences (capped).

## Document

One JSON object per page. Validation is `domain/knowledge/page.py`; the dashboard renders the body
with React components and never injects HTML, so the validator is what keeps a bad document out.

```jsonc
{
  "slug": "reference/frontend/next-server-client-boundaries", // <space>/<folders>/<note>, kebab-case
  "space": "reference",            // learn (_AI_Coach) | reference (_AI_Knowledge) | practice (_AI_Evaluations)
  "kind": "concept",               // topic concept decision catalogue moc roadmap hub coverage index
                                   // cheat-sheet quiz debrief case session guide note
  "title": "Next server and client boundaries",
  "group": "Frontend",             // folder / pack label; group_order and order sort inside a space
  "group_order": 1, "order": 1,
  "domain": "frontend",
  "summary": "One plain-text sentence or two",   // at most 600 characters
  "read_minutes": 4,
  "tags": [], "aliases": [],
  "links": ["reference/frontend/hydration"],     // outgoing slugs, drives backlinks
  "source_path": "_AI_Knowledge/Frontend/next-server-client-boundaries.md",
  "source_updated": "2026-09-30",
  "content_hash": "sha256 of the source note",
  "body": { "blocks": [], "outline": [{ "id": "why", "text": "Why", "level": 2 }], "related": [{ "slug": "...", "reason": "..." }] },
  "search_text": "plain text the search runs over, title and aliases first"
}
```

### Inline nodes

An inline array holds strings and these objects: `{t:"b"|"i"|"s", c:[...]}`, `{t:"code", v}`,
`{t:"a", href, c}` (`http(s)` and `mailto` only), `{t:"br"}`, `{t:"ref", slug, anchor?, auto?, c}` (a
link to another page; `auto` marks one inferred from a known term rather than written in the note)
and `{t:"missing", name, c}` (a link whose target is not in the library, such as one of Richard's own
notes: shown as plain text).

### Blocks

| `t` | Fields |
|---|---|
| `p`, `h` | `c` inline; `h` also `level` 1-6 and `id` |
| `ul`, `ol` | `items: [{c, checked?: "todo"\|"done"\|"partial", children: blocks}]` |
| `table` | `head`, `rows` (inline per cell), `align`, optional `marks` (index of a "Mark" column: a self-score column) |
| `code` | `lang`, `text` |
| `quote`, `callout` | `c: blocks`; callout has `tone` (`note`, `tip`, `warning`, `lead`...) and `title` |
| `section` | `variant`, `id`, `title`, `c: blocks`. Variants: `sits summary trap say firstchoice check sources links prompt ladder scoring reveal story terms` |
| `sits` | `rows: [{label, c}]` the "Where this sits" table |
| `ladder` | `items: [{id, q, a}]` guess-first probe ladder, `labels: {q, a}` |
| `reveal` | `title`, `hint`, `c: blocks` hidden until opened |
| `prompt` | `text`: what the interviewer says |
| `score` | `strong`, `fail` (lists of inline), `other` |
| `terms` | `items`: inline per term (the vocabulary self-score) |
| `facts` | `items: [{k, c}]` a metadata line such as Lens / Tests |
| `diagram` | positioned flow or sequence diagram (below) |
| `hr` | none |

### Diagrams

The publisher turns mermaid flowcharts, state diagrams and sequence diagrams into positioned data so
the dashboard draws plain SVG with no diagram library.

- Flow: `{kind:"flow", dir:"TD"|"LR", w, h, nodes:[{id,x,y,w,h,lines,shape}], edges:[{pts:[[x,y]...], label, lx, ly, style, arrow, back}], src}`
- Sequence: `{kind:"sequence", w, h, head, shift, participants:[{id,x,lines}], steps:[{type, y, x1, x2, ...}], src}`

## Setup

`scripts/sql/005_knowledge_library.sql` creates `knowledge_pages` (additive, idempotent). Apply it with
`scripts/apply_migration.py` before the first publish; the new endpoints fail until it exists and no
existing endpoint is affected either way.

Offline: `scripts/dev_fake_server.py --knowledge-file library.json` serves a converted library from
memory (see that script's header), with three synthetic pages when no file is given.
