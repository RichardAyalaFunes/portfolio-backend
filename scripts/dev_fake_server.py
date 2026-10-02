"""Offline dev server for the dashboard UI: the real dashboard router over fake data.

What it is
    A minimal FastAPI app that mounts only the dashboard router (plus CORS for the
    Vite dev server on port 5174) and swaps every Supabase-backed dependency for the
    in-memory fakes in tests/support/in_memory.py, seeded with SYNTHETIC data:
    invented companies and obviously fake people, never anything real. Routes, auth,
    validation and use cases are the production ones, so the React dashboard can be
    exercised end to end without a database.

    It never touches Supabase, never reads a .env file and makes no outbound network
    calls. State lives in memory and resets on every restart. It listens on
    127.0.0.1 unless you pass --host.

How to run (from the backend repo root)
    PYTHONPATH=src <python> scripts/dev_fake_server.py --port 8001

    The script also adds src/ and the repo root to sys.path itself, so a bare
    `<python> scripts/dev_fake_server.py` works too.

Credentials (obviously fake, override with environment variables)
    FAKE_DASHBOARD_PASSWORD   default: fake-dashboard-password
    FAKE_TOKEN_SECRET         default: fake-token-secret-at-least-32-bytes-long-000
    FAKE_INGEST_KEY           default: fake-ingest-key

    Log in with POST /api/dashboard/auth/login {"password": ..., "device_id": "any"},
    send the token as `Authorization: Bearer ...`. The agent-facing routes
    (POST /skill-match, POST /rules, POST /ingest ...) take `X-Ingest-Key`.

What is seeded
    41 roles (40 visible, 1 archived) in every state the UI has to handle: all six
    statuses, all five stages, every live_state, the three lanes (some with secondary
    lanes), every review tag, score bands, gate-dropped and below-bar rows, posted
    dates spread over the last 60 days, contacts and an application form on three
    roles, and two roles with a skill-match table. Plus ten search runs and a
    published search-rules document whose lines match the roles' discovery_queries,
    so the per-line stats are not empty. Application ids are derived from the
    identity key, so they stay the same across restarts.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for _path in (REPO_ROOT, REPO_ROOT / "src"):  # src ends up first on sys.path
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.domain.applications import identity  # noqa: E402
from backend.domain.applications.entities.job_application import JobApplication  # noqa: E402
from backend.domain.applications.skill_match import normalize_skill_match  # noqa: E402
from backend.domain.applications.value_objects import ApplicationId, Stage, Status  # noqa: E402
from backend.infrastructure.adapters.driver.rest.dashboard_controller import (  # noqa: E402
    router as dashboard_router,
)
from backend.infrastructure.config.dependencies import (  # noqa: E402
    get_application_repository,
    get_login_attempt_repository,
    get_postgrest_client,
    get_search_rules_repository,
    get_search_run_repository,
)
from backend.infrastructure.config.settings import Settings, get_settings  # noqa: E402
from tests.support.in_memory import (  # noqa: E402
    InMemoryApplicationRepository,
    InMemoryLoginAttemptRepository,
    InMemoryRulesRepository,
    InMemoryRunRepository,
)

DEFAULT_PASSWORD = "fake-dashboard-password"
DEFAULT_TOKEN_SECRET = "fake-token-secret-at-least-32-bytes-long-000"
DEFAULT_INGEST_KEY = "fake-ingest-key"
FRONTEND_ORIGINS = ["http://localhost:5174", "http://127.0.0.1:5174"]


def credential(env_name: str, default: str) -> str:
    """The env var when it is set and non-empty, else the documented fake default. An empty
    value never counts: an empty password or key would let anyone in."""
    return os.environ.get(env_name) or default

TODAY = date.today()
NOW = datetime.now(tz=timezone.utc)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


# -- search lines (shared by the roles' discovery_queries and the rules document) ------

AI_PERU = '"ai engineer" @peru'
AI_LATAM = '"ai engineer" @latam_remote'
AI_APPLIED_SA = '"applied ai engineer" @south_america'
AI_LLM = '"llm engineer" @peru'
AI_AGENTS = '"agent engineer" @worldwide_remote'
AI_LEGACY = '"ai developer" @peru'  # a line that was removed from the plan but still has history

FDE_LATAM = '"forward deployed engineer" @latam_remote'
FDE_SOLUTIONS = '"solutions engineer" ai @peru'
FDE_CUSTOMER = '"customer engineer" ai @south_america'
FDE_SHORT = '"fde" @worldwide_remote'
FDE_IMPL = '"implementation engineer" ai @latam_remote'

FOUND_LATAM = '"founding engineer" @latam_remote'
FOUND_AI = '"founding engineer" ai @worldwide_remote'
FOUND_FIRST = '"first engineer" startup @peru'
FOUND_YC = '"founding engineer" @yc_jobs'
FOUND_CTO = '"technical cofounder" ai @south_america'  # never surfaced a role: no stats row

# -- role texts, per lane ------------------------------------------------------------

LANE_TEXT: dict[str, dict[str, Any]] = {
    "ai_engineer": {
        "requirements": (
            "Design and ship LLM-backed product features: retrieval, tool use and evaluation. "
            "Python backend, a vector store, cloud deployment. 3+ years of backend experience."
        ),
        "why_apply": (
            "Backend-heavy AI role; the stack matches (Python, FastAPI, retrieval).",
            "Product team that ships LLM features to real users.",
            "Small team with direct ownership of the retrieval layer.",
        ),
        "why_not": (
            "Compensation is not stated.",
            "Seniority is unclear from the posting.",
            "The posting mentions heavy on-call duty.",
        ),
        "considerations": (
            "Confirm the timezone overlap before applying.",
            "Ask how evaluation is done today.",
            "Check whether the team is fully remote.",
        ),
    },
    "forward_deployed_engineer": {
        "requirements": (
            "Embed with customers, scope and ship integrations in weeks. Python or TypeScript, SQL, "
            "strong written English; travel up to 20%."
        ),
        "why_apply": (
            "Customer-facing delivery with real engineering ownership.",
            "Integration-heavy work that fits the backend track record.",
            "Early customer-facing team with a clear delivery playbook.",
        ),
        "why_not": (
            "Part of the time goes to support rather than building.",
            "Travel expectations are vague.",
            "Compensation is not stated.",
        ),
        "considerations": (
            "Ask how many customers each engineer carries.",
            "Check the on-site expectations.",
            "Confirm who owns the integrations after launch.",
        ),
    },
    "founding_engineer": {
        "requirements": (
            "First engineering hires: own the stack end to end, talk to users, ship weekly. "
            "Salary plus equity; small team."
        ),
        "why_apply": (
            "Broad ownership and direct access to the founders.",
            "Early product with real users and a clear AI angle.",
            "Equity on offer and a remote-first team.",
        ),
        "why_not": (
            "Pay may sit below the salary floor.",
            "Runway is unknown.",
            "Equity terms are not described.",
        ),
        "considerations": (
            "Ask about runway and the last round.",
            "Check the founders' availability for an intro call.",
            "Confirm how equity vests.",
        ),
    },
}
ELIGIBILITY = (
    "Open to candidates based in Latin America.",
    "Candidates must overlap at least 4 hours with US Eastern time.",
    "Worldwide remote; contractor agreement.",
)


# -- role builder --------------------------------------------------------------------


def _relative(age: int) -> str:
    if age == 0:
        return "3 hours ago"
    if age < 7:
        return f"{age} day{'s' if age > 1 else ''} ago"
    weeks = age // 7
    if age < 30:
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    return f"{max(age // 30, 1)} month{'s' if age >= 60 else ''} ago"


RUN_AGES = (0, 3, 7, 14, 21, 28, 35, 42, 49, 56)


def _run_age_for(age: int) -> int:
    """The earliest run on or after the posting date."""
    return max(run_age for run_age in RUN_AGES if run_age <= age)


def _url(source: str, n: int) -> str:
    posting_id = str(9_000_000 + n)
    if source == "wellfound":
        return f"https://boards.example.com/wellfound/jobs/{posting_id}"
    if source == "yc":
        return f"https://startups.example.com/jobs/{posting_id}"
    return f"https://jobs.example.com/jobs/view/{posting_id}"  # matches the /jobs/view/<id> resolver


def role(
    n: int,
    company: str,
    title: str,
    lane: Optional[str],
    score: Optional[int],
    *,
    status: str = "To validate",
    stage: str = "Not applied",
    age: int = 2,
    source: str = "linkedin",
    live: Optional[str] = "LISTED",
    queries: tuple[str, ...] = (),
    secondary: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    mode: str = "Remote",
    where: str = "Remote (LATAM)",
    pay: Optional[str] = None,
    employment: str = "Full-time",
    drop: Optional[tuple[str, str]] = None,
    note: str = "",
    reviewed: Optional[int] = None,
    archived: bool = False,
    extras: Optional[dict[str, Any]] = None,
    **more: Any,
) -> JobApplication:
    """One synthetic role. `age` is days since it was posted; `reviewed` is days since
    Richard last touched it. `more` passes straight to JobApplication (contacts, ...)."""
    key = identity.identity_key({"company": company, "title": title})
    posted = days_ago(age)
    run_age = _run_age_for(age)
    dead = live in ("CLOSED", "SUSPENDED", "GONE") or status in ("Cold", "Dropped")
    url = _url(source, n)
    texts = LANE_TEXT.get(lane or "", LANE_TEXT["ai_engineer"])

    if status == "Flagged":
        band: Optional[str] = "flagged"
    elif score is None:
        band = "dropped" if status == "Dropped" else None
    else:
        band = "excellent" if score >= 90 else "good" if score >= 75 else "below"

    why_not = texts["why_not"][n % 3]
    why_apply: Optional[str] = texts["why_apply"][n % 3]
    if drop is not None and drop[0] == "read":
        why_apply, why_not = None, f"Dropped at the {drop[0]} stage: {drop[1]}."
    elif drop is not None:
        why_not = f"Scored {score}, below the pass bar."

    return JobApplication(
        id=ApplicationId(value=uuid.uuid5(uuid.NAMESPACE_URL, f"dashboard-fake:{key}")),
        identity_key=key,
        title=title,
        company=company,
        status=Status(status),
        application_stage=Stage(stage),
        group=lane,
        score=score,
        band=band,
        location_text=where,
        work_mode=mode,
        employment_type=employment,
        salary_text=pay,
        posted_date=posted,
        posted_date_source="derived_from_relative",
        posted_relative=_relative(age),
        eligibility_text=ELIGIBILITY[n % 3],
        requirements_excerpt=texts["requirements"],
        why_apply=why_apply,
        why_not=why_not,
        considerations=texts["considerations"][n % 3],
        jd_url=url,
        source=source,
        found_by_query=queries[0] if queries else None,
        run_date=days_ago(run_age),
        first_seen=days_ago(run_age),
        last_seen=days_ago(run_age) if dead else TODAY,
        live_state=live,
        live_checked_at=days_ago(1) if live else None,
        work_remote_allowed=(mode == "Remote") if live else None,
        drop_stage=drop[0] if drop else None,
        drop_reason=drop[1] if drop else None,
        notes=note,
        notes_updated_at=days_ago(reviewed if reviewed is not None else 1) if note else None,
        postings=[
            {
                "id": str(9_000_000 + n),
                "url": url,
                "source": source,
                "run_date": days_ago(run_age).isoformat(),
                "posted_date": posted.isoformat(),
                "live_state": live,
            }
        ],
        extras=dict(extras or {}),
        secondary_lanes=list(secondary),
        discovery_queries=list(queries),
        tags=list(tags),
        reviewed_at=NOW - timedelta(days=reviewed) if reviewed is not None else None,
        archived_at=NOW - timedelta(days=2) if archived else None,
        **more,
    )


# -- contacts, application form, skill-match tables ----------------------------------


def contacts_for(slug: str, company: str, *, sent_first: bool = False) -> list[dict[str, Any]]:
    people = (
        ("Alex Demo", "Head of Engineering", "hiring_manager", "Leads the team this role reports to."),
        ("Sam Sample", "Senior Technical Recruiter", "recruiter", "Runs the interview loop for engineering roles."),
    )
    contacts = []
    for rank, (name, job_title, category, reason) in enumerate(people, start=1):
        person = name.lower().replace(" ", "-")
        contacts.append(
            {
                "id": f"{slug}-c{rank}",
                "name": name,
                "title": job_title,
                "linkedin_url": f"https://people.example.com/in/{person}-{slug}",
                "linkedin_slug": f"{person}-{slug}",
                "connection_degree": 2 if rank == 1 else 3,
                "mutual_connections": 4 - rank,
                "category": category,
                "priority_rank": rank,
                "reason": reason,
                "message_draft": (
                    f"Hi {name.split()[0]}, I saw the opening at {company} and the work on retrieval-backed "
                    "products caught my eye. Happy to share a short summary of what I have shipped if useful."
                ),
                "outreach_stage": "Sent" if (sent_first and rank == 1) else None,
                "outreach_stage_updated_at": days_ago(2).isoformat() if (sent_first and rank == 1) else None,
                "source": "company_team_page",
                "found_at": days_ago(1).isoformat(),
            }
        )
    return contacts


def application_form_for(slug: str) -> dict[str, Any]:
    return {
        "apply_type": "company_form",
        "apply_url": f"https://careers.example.com/{slug}/apply",
        "checked_at": days_ago(1).isoformat(),
        "skipped_reason": None,
        "questions": [
            {
                "question": "Why are you interested in this role?",
                "required": True,
                "field_type": "textarea",
                "classification": "substantive",
                "answer_bullets": [
                    "Built and operated a retrieval-backed assistant with its own evaluation harness",
                    "Wants to work closer to users than a pure platform role allows",
                ],
                "answer_draft": (
                    "I have spent the last two years putting retrieval and tool use into production "
                    "backends, and this role is the same problem closer to the customer."
                ),
            },
            {
                "question": "Do you require visa sponsorship?",
                "required": True,
                "field_type": "select",
                "classification": "trivial",
                "answer_bullets": [],
                "answer_draft": "No",
            },
        ],
    }


SKIPPED_FORM = {
    "apply_type": "linkedin_easy_apply",
    "apply_url": None,
    "checked_at": days_ago(0).isoformat(),
    "skipped_reason": "LinkedIn Easy Apply is skipped by policy; apply on the company site instead.",
    "questions": [],
}


def _row(requirement, kind, match, match_evidence, cv, linkedin):
    """Compact row builder: `cv` and `linkedin` are (level, evidence, fix) tuples."""
    return {
        "requirement": requirement,
        "kind": kind,
        "match": {"level": match, "evidence": match_evidence},
        "cv": {"level": cv[0], "evidence": cv[1], "fix": cv[2]},
        "linkedin": {"level": linkedin[0], "evidence": linkedin[1], "fix": linkedin[2]},
    }


SKILL_MATCH_AI_ENGINEER = {
    "analyzed_on": days_ago(1).isoformat(),
    "verdict": (
        "Buen encaje técnico. Lo que más pesa para quien filtra el CV (LangGraph, pgvector, despliegue en la "
        "nube) existe en la experiencia real, pero el CV y LinkedIn lo muestran a medias."
    ),
    "cv_used": "demo-cv-ai-engineer.pdf (fake, v14)",
    "linkedin_used": "demo LinkedIn profile snapshot (fake)",
    "jd_source": "full_text",
    "rows": [
        _row(
            "Python, typed and tested; FastAPI", "must", "strong",
            "Seis años con Python en producción, tipado con mypy y pruebas con pytest; API con FastAPI en el backend del portafolio.",
            ("shown", "La sección de Skills lista Python, FastAPI y pytest, y el proyecto del portafolio lo respalda.", None),
            ("partial", "Python aparece en Skills, pero FastAPI y pytest no.",
             "Add FastAPI and pytest to the LinkedIn Skills list and mention them in the current role's description."),
        ),
        _row(
            "Hands-on LLM application development (RAG, tool use, evaluation)", "must", "strong",
            "Asistente con RAG, herramientas y un arnés de evaluación con casos dorados, desplegado en el portafolio.",
            ("shown", "El CV describe el asistente con RAG y la evaluación automatizada.", None),
            ("shown", "El resumen y el rol actual mencionan RAG y evaluación.", None),
        ),
        _row(
            "Production experience with agent frameworks (LangGraph or similar)", "must", "partial",
            "Proyecto propio con LangGraph y grafos con puntos de control; sin despliegue para un cliente.",
            ("partial", "El CV habla de agentes sin nombrar LangGraph ni dar un resultado.",
             "Name LangGraph in the portfolio project bullet and add one measurable outcome (latency or cost per run)."),
            ("missing", "LinkedIn no menciona agentes ni LangGraph.",
             "Add a Featured item or a role bullet that describes the LangGraph agent project and its outcome."),
        ),
        _row(
            "Vector search and retrieval quality (pgvector, hybrid search)", "must", "strong",
            "Búsqueda híbrida con pgvector y reranking en el chatbot del portafolio, con recall medido.",
            ("missing", "El CV no menciona pgvector ni búsqueda híbrida.",
             "Add 'pgvector, hybrid search and reranking' to the portfolio project bullet."),
            ("partial", "El resumen dice 'vector search' sin más detalle.",
             "Replace the generic 'vector search' wording with pgvector and hybrid retrieval, plus the recall figure."),
        ),
        _row(
            "Cloud deployment (AWS or GCP), Docker, CI/CD", "must", "partial",
            "Docker y despliegue en plataformas gestionadas en proyectos propios; sin AWS ni GCP en producción.",
            ("shown", "El CV lista Docker y CI/CD con GitHub Actions.", None),
            ("shown", "Skills incluye Docker y CI/CD.", None),
        ),
        _row(
            "Observability and cost control for LLM workloads", "nice", "gap",
            "Sin experiencia propia con trazabilidad de LLM ni control de costos en producción.",
            ("na", None, None),
            ("na", None, None),
        ),
        _row(
            "Professional fluency in Spanish and English", "must", "strong",
            "Inglés profesional a diario y español nativo; entrevistas y documentación en ambos idiomas.",
            ("shown", "El CV está en inglés e incluye la sección de idiomas.", None),
            ("shown", "La sección de idiomas de LinkedIn lo muestra.", None),
        ),
        _row(
            "Mentoring or leading a small engineering team", "nice", "partial",
            "Mentoría informal a dos ingenieros junior; sin un rol formal de liderazgo.",
            ("missing", "El CV no menciona mentoría.",
             "Add a one-line mentoring bullet to the current role (two junior engineers, onboarding plan)."),
            ("missing", "LinkedIn no menciona mentoría.", "Mention mentoring in the About section."),
        ),
    ],
}

SKILL_MATCH_FDE = {
    "analyzed_on": days_ago(1).isoformat(),
    "verdict": (
        "Encaje sólido en entrega técnica con clientes. Falta evidencia visible de procesos de seguridad "
        "empresarial, y el CV esconde el trabajo de integraciones."
    ),
    "cv_used": "demo-cv-forward-deployed.pdf (fake, v9)",
    "linkedin_used": "demo LinkedIn profile snapshot (fake)",
    "jd_source": "excerpt",
    "rows": [
        _row(
            "Customer-facing technical delivery (discovery calls, demos, workshops)", "must", "strong",
            "Demos y talleres técnicos con clientes en los dos últimos roles; descubrimiento de requisitos antes de construir.",
            ("partial", "El CV habla de 'colaboración con clientes' sin cifras ni ejemplos.",
             "Add one bullet with a customer outcome, for example an integration live in three weeks and its usage."),
            ("shown", "La descripción del rol actual cita demos y talleres con clientes.", None),
        ),
        _row(
            "Integrations: REST, webhooks, SSO, data pipelines", "must", "strong",
            "Integraciones REST y webhooks con terceros; pipelines de datos con Python y SQL.",
            ("shown", "El CV lista integraciones REST y webhooks.", None),
            ("partial", "LinkedIn menciona 'integraciones' en general.",
             "List webhooks and SSO integrations in Skills and in the role description."),
        ),
        _row(
            "SQL and data modelling", "must", "strong",
            "Modelado relacional en Postgres, migraciones e índices; consultas analíticas a diario.",
            ("shown", "El CV lista Postgres y modelado de datos.", None),
            ("shown", "Skills incluye PostgreSQL y SQL.", None),
        ),
        _row(
            "Prototype to production in weeks; owns the outcome", "must", "strong",
            "Prototipos llevados a producción en semanas, con responsabilidad de extremo a extremo y soporte posterior.",
            ("partial", "El CV muestra entregas, pero no deja explícita la responsabilidad posterior.",
             "Make ownership explicit: 'owned delivery from prototype to production support'."),
            ("missing", "LinkedIn no menciona responsabilidad de extremo a extremo.",
             "Add the same ownership line to the experience section."),
        ),
        _row(
            "Enterprise onboarding: security reviews, DPAs, procurement", "must", "gap",
            "Sin experiencia directa con revisiones de seguridad ni acuerdos de datos con clientes grandes.",
            ("missing", "No aparece, y tampoco hay experiencia que mostrar.", None),
            ("missing", "No aparece, y tampoco hay experiencia que mostrar.", None),
        ),
        _row(
            "Python or TypeScript", "must", "strong",
            "Python a diario; TypeScript en el frontend del portafolio.",
            ("shown", "El CV lista ambos lenguajes.", None),
            ("shown", "Skills incluye Python y TypeScript.", None),
        ),
        _row(
            "Travel up to 25% across LATAM", "nice", "partial",
            "Disponibilidad para viajes ocasionales; el 25% no está confirmado.",
            ("na", None, None),
            ("na", None, None),
        ),
        _row(
            "Technical writing: runbooks, solution docs", "nice", "partial",
            "Documentos de arquitectura y guías de operación en proyectos propios.",
            ("missing", "El CV no menciona documentación técnica.",
             "Add 'runbooks and solution docs' to the skills line."),
            ("partial", "Aparece 'documentation' sin ejemplos.", "Link one public design doc or runbook in Featured."),
        ),
    ],
}


# -- the 41 roles --------------------------------------------------------------------


def build_roles() -> list[JobApplication]:
    fathom = role(
        6, "Fathom Peak AI", "Applied AI Engineer", "ai_engineer", 86, status="Approved", age=2,
        queries=(AI_APPLIED_SA,), reviewed=1, pay="USD 5,000 - 6,500 / month",
    )
    return [
        # -- 90+ band, active pipeline
        role(1, "Acme Robotics", "Applied AI Engineer", "ai_engineer", 94, status="Approved", stage="Interviewing",
             age=3, queries=(AI_PERU, AI_LATAM), secondary=("founding_engineer",), pay="USD 6,500 - 8,000 / month",
             reviewed=2, note="Intro call done; technical round next week.",
             contacts=contacts_for("acme-robotics", "Acme Robotics", sent_first=True),
             application_form=application_form_for("acme-robotics")),
        role(2, "Brightwave Analytics", "AI Engineer, LLM Platform", "ai_engineer", 92, age=0,
             queries=(AI_LATAM, AI_APPLIED_SA), tags=("salary_unknown",),
             contacts=contacts_for("brightwave", "Brightwave Analytics"), application_form=SKIPPED_FORM,
             skill_match=normalize_skill_match(SKILL_MATCH_AI_ENGINEER, today=TODAY)),
        role(3, "Cobalt Harbor Labs", "Forward Deployed Engineer", "forward_deployed_engineer", 91, age=1,
             queries=(FDE_LATAM, FDE_SHORT), pay="USD 5,500 - 7,500 / month",
             skill_match=normalize_skill_match(SKILL_MATCH_FDE, today=TODAY)),
        role(4, "Driftwood Systems", "Founding Engineer, AI Products", "founding_engineer", 90, status="Approved",
             stage="Applied", age=6, source="wellfound", queries=(FOUND_LATAM, FOUND_AI),
             pay="USD 4,500 - 6,000 / month + equity", reviewed=5,
             note="Applied through the company form; waiting for a reply."),
        # -- 75-89 band
        role(5, "Evergreen Telemetry", "Agent Engineer", "ai_engineer", 88, age=0, queries=(AI_AGENTS, AI_LATAM),
             secondary=("forward_deployed_engineer",), tags=("language_mixed",), where="Remote (Spain and LATAM)"),
        fathom,
        role(7, "Granite Loop", "LLM Engineer", "ai_engineer", 85, status="Rejected", age=9, queries=(AI_LLM,),
             mode="On-site", where="On-site, Austin (relocation required)", reviewed=6,
             note="On-site in another country; not workable."),
        role(8, "Helio Forge", "Solutions Engineer, AI", "forward_deployed_engineer", 84, age=2,
             queries=(FDE_SOLUTIONS,), secondary=("ai_engineer",), tags=("company_type_unclear",)),
        role(9, "Ironleaf Software", "Forward Deployed AI Engineer", "forward_deployed_engineer", 83,
             status="Approved", stage="Offer", age=21, queries=(FDE_LATAM,), pay="USD 5,500 - 6,000 / month",
             reviewed=3, note="Offer received: USD 5,800 per month. Deciding by Friday."),
        role(10, "Juniper Relay", "Founding Engineer", "founding_engineer", 82, age=3, source="yc",
             live="UNVERIFIABLE", queries=(FOUND_YC,), tags=("salary_unknown", "company_type_unclear")),
        role(11, "Kestrel Canvas", "AI Engineer", "ai_engineer", 81, status="Flagged", age=1, queries=(AI_PERU,),
             tags=("location_unsure",), where="Remote (US only?)"),
        role(12, "Lumen Quarry", "Senior AI Engineer", "ai_engineer", 80, age=4, live=None,
             queries=(AI_PERU, AI_LATAM), tags=("big_corporate",)),
        role(13, "Marlin Grid", "Customer Engineer, AI", "forward_deployed_engineer", 79, status="Rejected", age=12,
             queries=(FDE_CUSTOMER,), reviewed=8, note="Mostly support work, not engineering."),
        role(14, "Nimbus Ledger", "Founding AI Engineer", "founding_engineer", 78, age=5, source="wellfound",
             queries=(FOUND_LATAM,)),
        role(15, "Orchid Compute", "ML Engineer (LLM Systems)", "ai_engineer", 77, status="Flagged", age=2,
             queries=(AI_LLM,), tags=("language_mixed", "location_unsure")),
        role(16, "Paperkite Health", "AI Engineer", "ai_engineer", 76, age=7, queries=(AI_PERU,)),
        role(17, "Quill Harbor", "Forward Deployed Engineer", "forward_deployed_engineer", 75, status="Approved",
             stage="Applied", age=14, queries=(FDE_LATAM, FDE_SOLUTIONS), reviewed=10,
             note="Applied; the recruiter replied asking for availability."),
        role(18, "Redwood Signal", "AI Platform Engineer", "ai_engineer", 89, status="Approved", stage="Closed",
             age=26, live="CLOSED", queries=(AI_LATAM,), reviewed=12, note="Rejected after the technical round."),
        role(19, "Saffron Data", "Founding Engineer", "founding_engineer", 87, status="Rejected", age=16,
             source="yc", live="UNVERIFIABLE", queries=(FOUND_YC,), reviewed=14, note="Pay is below the floor."),
        # -- retired by the liveness sweep
        role(20, "Tidepool Works", "Agentic Workflows Engineer", "ai_engineer", 82, status="Cold", age=20,
             live="CLOSED", queries=(AI_AGENTS,),
             extras={"status_previous": "To validate", "cold_reason": f"posting closed (verified {days_ago(1)})"}),
        role(21, "Umber Stack", "Solutions Architect, AI", "forward_deployed_engineer", 80, status="Cold", age=33,
             live="SUSPENDED", queries=(FDE_SOLUTIONS,),
             extras={"status_previous": "Flagged", "cold_reason": f"posting closed (verified {days_ago(2)})"}),
        role(22, "Vantage Orchard", "Founding Engineer", "founding_engineer", 79, status="Cold", age=41,
             source="wellfound", live="GONE", queries=(FOUND_FIRST,),
             extras={"status_previous": "To validate", "cold_reason": f"posting closed (verified {days_ago(3)})"}),
        role(23, "Willow Circuit", "Applied AI Engineer", "ai_engineer", 91, status="Flagged", age=3,
             queries=(AI_APPLIED_SA, AI_PERU), tags=("big_corporate", "salary_unknown")),
        # -- scored below the pass bar (55-74)
        role(24, "Xylo Freight", "AI Engineer", "ai_engineer", 73, status="Dropped", age=8, live=None,
             queries=(AI_PERU,), drop=("scored", "below_bar")),
        role(25, "Yarrow Cloud", "Forward Deployed Engineer", "forward_deployed_engineer", 70, status="Dropped",
             age=18, live=None, queries=(FDE_CUSTOMER,), drop=("scored", "below_bar")),
        role(26, "Zephyr Mills", "Founding Engineer", "founding_engineer", 66, status="Dropped", age=29,
             source="wellfound", live=None, queries=(FOUND_FIRST,), drop=("scored", "below_bar")),
        role(27, "Atlas Parcel", "LLM Applications Engineer", "ai_engineer", 58, status="Dropped", age=45,
             live=None, queries=(AI_LLM,), drop=("scored", "below_bar")),
        # -- dropped at a gate while reading the posting (never scored)
        role(28, "Beacon Tiller", "Backend Engineer, AI Infrastructure", "ai_engineer", None, status="Dropped",
             age=1, live=None, queries=(AI_LATAM,), drop=("read", "eligibility_geo"),
             where="Remote (US residents only)"),
        role(29, "Cinder Vale", "AI Engineer", "ai_engineer", None, status="Dropped", age=4, live=None,
             queries=(AI_PERU,), drop=("read", "stack_paradigm")),
        role(30, "Dune Harbor", "Machine Learning Researcher", None, None, status="Dropped", age=10, live=None,
             queries=(AI_LLM,), drop=("read", "off_lane")),
        role(31, "Ember Quay", "AI Engineer", "ai_engineer", None, status="Dropped", age=13, live=None,
             queries=(AI_LATAM,), drop=("read", "deal_breaker"), mode="On-site",
             where="On-site, Berlin (relocation required)"),
        role(32, "Fennel Row", "Staff AI Engineer (contract via agency)", "ai_engineer", None, status="Dropped",
             age=22, live=None, queries=(AI_APPLIED_SA,), drop=("read", "staffing_pool"), employment="Contract"),
        # -- the rest of the mix
        role(33, "Garnet Field", "Forward Deployed Engineer", "forward_deployed_engineer", 86, status="Approved",
             stage="Applied", age=11, queries=(FDE_LATAM,), reviewed=7,
             note="Applied with a tailored cover note.",
             contacts=contacts_for("garnet-field", "Garnet Field"),
             application_form=application_form_for("garnet-field")),
        role(34, "Harbor Mist", "AI Engineer", "ai_engineer", 84, age=35, queries=(AI_PERU,)),
        role(35, "Indigo Wharf", "Founding Engineer", "founding_engineer", 83, age=52, source="wellfound", live=None,
             queries=(FOUND_AI,)),
        role(36, "Jasper Dock", "AI Engineer", "ai_engineer", 77, status="Rejected", age=59, live="GONE",
             queries=(AI_PERU, AI_LEGACY), reviewed=50, note="Seniority bar was too high."),
        role(37, "Fathom Peak AI", "Applied AI Engineer (Platform)", "ai_engineer", 88, age=0,
             queries=(AI_APPLIED_SA,), extras={"possible_duplicate_of": str(fathom.id)}),
        role(38, "Linen Peak", "Forward Deployed Engineer", "forward_deployed_engineer", 92, age=1,
             queries=(FDE_LATAM, FDE_IMPL)),
        role(39, "Moss Lantern", "Founding Engineer", "founding_engineer", 85, status="Flagged", age=5,
             queries=(FOUND_LATAM,), tags=("location_unsure", "salary_unknown")),
        role(40, "Nectar Gate", "AI Engineer", "ai_engineer", 81, status="Approved", age=4, live="CLOSED",
             queries=(AI_LATAM, AI_PERU), reviewed=3, note="Approved before the posting closed; worth a look."),
        # -- deleted by Richard (archived): hidden from the list, still counted in per-line stats
        role(41, "Oak Meridian", "AI Engineer", "ai_engineer", 72, status="Rejected", age=30, queries=(AI_PERU,),
             reviewed=20, note="Deleted: duplicate of another posting.", archived=True),
    ]


# -- search runs ---------------------------------------------------------------------


def build_runs() -> list[dict[str, Any]]:
    runs = []
    for index, run_age in enumerate(RUN_AGES):
        surfaced = 118 - index * 6
        opened = 34 - index * 2
        run: dict[str, Any] = {
            "run_date": days_ago(run_age).isoformat(),
            "label": f"Search run {len(RUN_AGES) - index}",
            "approx": False,
            "searches_run": 15 - index % 3,
            "cards_surfaced": surfaced,
            "cards_opened": opened,
            "jd_extracted": opened - 3,
            "card_screens": {"seen": surfaced, "title_screen_dropped": surfaced - opened - 22, "duplicates": 22},
            "portals": ["linkedin", "wellfound", "yc"] if index % 2 == 0 else ["linkedin"],
            "notes": "Synthetic run for the offline dev server." if index == 0 else None,
            "validated_account": "demo-account",
            "browser_surface": "browser-pane",
            "outcome": {},
            "line_yield": [],
            "plan_changes": [],
        }
        if index < 3:  # only recent runs carry the feedback-loop fields (added in migration 003)
            run["outcome"] = {
                "passed": 6 - index, "flagged": 3, "borderline": 2, "dropped": 14 + index,
                "jds_read": opened - 3, "target_met": index != 2,
            }
            run["line_yield"] = [
                {"line": AI_PERU, "portal": "linkedin", "surfaced": 24 - index, "new_after_dedupe": 6 - index,
                 "read": 5, "passed": 2, "flagged": 1},
                {"line": FDE_LATAM, "portal": "linkedin", "surfaced": 19, "new_after_dedupe": 4, "read": 4,
                 "passed": 2 - index % 2, "flagged": 0},
                {"line": FOUND_LATAM, "portal": "wellfound", "surfaced": 11, "new_after_dedupe": 3, "read": 3,
                 "passed": 1, "flagged": 1},
            ]
        if index == 0:
            run["plan_changes"] = [
                {"action": "add", "line": AI_AGENTS,
                 "reason": "Several passing roles use 'agent engineer' as the title.",
                 "evidence": "3 of the last 8 passes carried the title."},
                {"action": "retire", "line": FDE_SHORT,
                 "reason": "Two runs without a single read posting.", "evidence": "0 of 9 cards read."},
            ]
        runs.append(run)
    return runs


# -- the published search-rules document ---------------------------------------------


def _line(
    text: str,
    status: str,
    *,
    portal: str = "linkedin",
    origin: str = "standing",
    added: Optional[str] = None,
    reason: Optional[str] = None,
    evidence: Optional[str] = None,
    runs: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "line": text, "portal": portal, "status": status, "origin": origin,
        "added": added, "reason": reason, "evidence": evidence, "runs": runs,
    }


def build_rules() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "config_updated_at": days_ago(14).isoformat(),
        "thresholds": {
            "excellent_bar": 90, "pass_bar": 75, "second_opinion_band": [65, 74], "didnt_pass_floor": 55,
            "skill_match_min_score": 60, "enrichment_min_score": 80,
            "salary_floor_usd_month": 4000, "salary_target_usd_month": "5000 to 8000",
        },
        "scope": {
            "freshness_default_days": 3,
            "freshness_max_days": 7,
            "anchors": [
                {"id": "peru", "label": "Peru"},
                {"id": "latam_remote", "label": "Remote, LATAM"},
                {"id": "south_america", "label": "South America"},
                {"id": "worldwide_remote", "label": "Remote, worldwide"},
            ],
            "portals": [
                {"id": "linkedin", "tier": 1, "label": "LinkedIn"},
                {"id": "wellfound", "tier": 2, "label": "Wellfound"},
                {"id": "yc", "tier": 2, "label": "Startup job board"},
            ],
            "never": [
                "Roles that require relocation",
                "Staffing agencies and body-shop contracts",
                "Roles posted more than seven days ago",
            ],
        },
        "lanes": [
            {
                "id": "ai_engineer", "order": 1, "label": "AI Engineer",
                "thesis": "Backend engineers who put LLMs into products: retrieval, agents and evaluation.",
                "looks_for": "Applied AI or LLM engineering inside a product team, Python backend, remote-friendly for LATAM.",
                "excludes": "Pure research roles, data-labelling work and roles that ask for a PhD.",
                "title_synonyms": ["ai engineer", "applied ai engineer", "llm engineer", "agent engineer", "ml engineer (llm)"],
                "lines": [
                    _line(AI_PERU, "standing"),
                    _line(AI_LATAM, "standing"),
                    _line(AI_APPLIED_SA, "standing"),
                    _line(AI_LLM, "weekly"),
                    _line(AI_AGENTS, "trial", origin="adaptive", added=days_ago(3).isoformat(),
                          reason="Several passing roles use 'agent engineer' as the title.",
                          evidence="3 of the last 8 passes carried the title.", runs=1),
                ],
                "rubric": [
                    {"dimension": "Stack and paradigm fit", "weight": 25},
                    {"dimension": "Role scope and seniority", "weight": 20},
                    {"dimension": "Eligibility (where you can work)", "weight": 20},
                    {"dimension": "Compensation against the floor", "weight": 15},
                    {"dimension": "Company stage and quality", "weight": 10},
                    {"dimension": "Posting freshness and clarity", "weight": 10},
                ],
                "rules": [
                    {"title": "Keep when", "kind": "keep", "items": [
                        "The role ships LLM features to real users",
                        "Python is the main backend language",
                        "The team is remote-friendly for LATAM",
                    ]},
                    {"title": "Drop when", "kind": "drop", "items": [
                        "The work is model research or data labelling",
                        "The stack is built around a paradigm we do not use",
                    ]},
                    {"title": "Reviewer notes", "kind": "note", "items": [
                        "Roles at large corporations get the big_corporate tag instead of being dropped",
                    ]},
                ],
            },
            {
                "id": "forward_deployed_engineer", "order": 2, "label": "Forward Deployed Engineer",
                "thesis": "Engineers embedded with customers who still own the code they ship.",
                "looks_for": "Integration-heavy delivery with real engineering ownership and a clear scope.",
                "excludes": "Support roles, pure pre-sales and roles with constant travel.",
                "title_synonyms": ["forward deployed engineer", "solutions engineer", "customer engineer", "implementation engineer", "fde"],
                "lines": [
                    _line(FDE_LATAM, "standing"),
                    _line(FDE_SOLUTIONS, "standing"),
                    _line(FDE_CUSTOMER, "weekly"),
                    _line(FDE_IMPL, "trial", origin="adaptive", added=days_ago(10).isoformat(),
                          reason="Implementation titles overlap with forward deployed work.",
                          evidence="2 reads, 1 pass.", runs=2),
                    _line(FDE_SHORT, "retired", origin="adaptive", added=days_ago(40).isoformat(),
                          reason="Two runs without a single read posting.", evidence="0 of 9 cards read.", runs=4),
                ],
                "rubric": [
                    {"dimension": "Customer-facing scope", "weight": 25},
                    {"dimension": "Technical depth", "weight": 20},
                    {"dimension": "Eligibility (where you can work)", "weight": 20},
                    {"dimension": "Compensation against the floor", "weight": 15},
                    {"dimension": "Company stage and quality", "weight": 10},
                    {"dimension": "Posting clarity", "weight": 10},
                ],
                "rules": [
                    {"title": "Keep when", "kind": "keep", "items": [
                        "Engineers own integrations end to end",
                        "Travel is occasional and stated",
                    ]},
                    {"title": "Drop when", "kind": "drop", "items": [
                        "More than a quarter of the time goes to support tickets",
                        "The role is sales engineering with a quota",
                    ]},
                ],
            },
            {
                "id": "founding_engineer", "order": 3, "label": "Founding Engineer",
                "thesis": "Early teams where one engineer owns the stack and talks to users.",
                "looks_for": "A funded early-stage company with real users and founders who write code or ship weekly.",
                "excludes": "Equity-only offers and companies with no stated runway.",
                "title_synonyms": ["founding engineer", "first engineer", "technical cofounder"],
                "lines": [
                    _line(FOUND_LATAM, "standing"),
                    _line(FOUND_AI, "standing"),
                    _line(FOUND_FIRST, "weekly", portal="wellfound"),
                    _line(FOUND_YC, "standing", portal="yc"),
                    _line(FOUND_CTO, "retired", portal="wellfound", origin="adaptive",
                          added=days_ago(35).isoformat(), reason="Cofounder searches mostly surface equity-only roles.",
                          evidence="0 passes in 5 runs.", runs=5),
                ],
                "rubric": [
                    {"dimension": "Ownership and scope", "weight": 25},
                    {"dimension": "Stack fit", "weight": 20},
                    {"dimension": "Eligibility (where you can work)", "weight": 15},
                    {"dimension": "Compensation and equity", "weight": 20},
                    {"dimension": "Founders and traction", "weight": 10},
                    {"dimension": "Posting clarity", "weight": 10},
                ],
                "rules": [
                    {"title": "Keep when", "kind": "keep", "items": [
                        "There is a stated salary next to the equity",
                        "The company has users or revenue",
                    ]},
                    {"title": "Drop when", "kind": "drop", "items": [
                        "The offer is equity only",
                        "The company has no stated runway",
                    ]},
                ],
            },
        ],
        "gates": [
            {"id": "eligibility", "order": 1, "name": "Where you can work",
             "summary": "The role must be open to candidates in Peru or remote across LATAM.",
             "drop_reasons": ["eligibility_geo", "country_locked"],
             "details": ["Remote roles restricted to one country are dropped", "Timezone overlap above six hours is dropped"],
             "lane_notes": {"founding_engineer": "Founders sometimes accept a different country; flag instead of dropping."}},
            {"id": "title_screen", "order": 2, "name": "Title screen",
             "summary": "Cheap check on the card title before opening the posting.",
             "drop_reasons": ["title_screen"], "details": ["Blocklisted title terms are dropped without reading the posting"],
             "lane_notes": {}},
            {"id": "stack_paradigm", "order": 3, "name": "Stack and paradigm",
             "summary": "The core stack must be one we work in.",
             "drop_reasons": ["stack_paradigm"], "details": ["Roles built around a stack we do not use are dropped"],
             "lane_notes": {}},
            {"id": "lane_fit", "order": 4, "name": "Lane fit",
             "summary": "The role has to belong to one of the three lanes.",
             "drop_reasons": ["off_lane"], "details": ["Research and data-labelling roles are off lane"],
             "lane_notes": {"ai_engineer": "Applied research with a product owner can still pass."}},
            {"id": "staffing", "order": 5, "name": "Staffing pools and agencies",
             "summary": "Direct employers only.",
             "drop_reasons": ["staffing_pool"], "details": ["Agency and body-shop postings are dropped"],
             "lane_notes": {}},
            {"id": "deal_breakers", "order": 6, "name": "Deal breakers",
             "summary": "Anything on the deal-breaker list ends the review.",
             "drop_reasons": ["deal_breaker"], "details": ["See the deal-breaker list"], "lane_notes": {}},
            {"id": "score_bar", "order": 7, "name": "Score bar",
             "summary": "Roles below the pass bar are kept as 'didn't pass' above the floor.",
             "drop_reasons": ["below_bar"], "details": ["Pass bar 75, floor 55, second-opinion band 65 to 74"],
             "lane_notes": {}},
            {"id": "freshness", "order": 8, "name": "Freshness and duplicates",
             "summary": "Old postings and reposts are not worth a review.",
             "drop_reasons": ["stale_posting", "duplicate"],
             "details": ["Posted more than seven days ago is dropped", "Reposts fold into the existing role"],
             "lane_notes": {}},
        ],
        "deal_breakers": [
            "Mandatory relocation or on-site work outside LATAM",
            "Unpaid trial projects",
            "Commission-only compensation",
            "Roles that require a security clearance",
        ],
        "review_tags": [
            {"id": "location_unsure", "when": "The posting does not say where the employee may live.",
             "effect": "Flagged for review instead of passing."},
            {"id": "company_type_unclear", "when": "Cannot tell whether the employer is a product company.",
             "effect": "Flagged for review."},
            {"id": "salary_unknown", "when": "No pay range anywhere in the posting.", "effect": "Tag only; the score is unchanged."},
            {"id": "big_corporate", "when": "The employer has more than 1,000 people.", "effect": "Tag only."},
            {"id": "language_mixed", "when": "The posting mixes Spanish and English requirements.", "effect": "Tag only."},
        ],
        "blocklists": {
            "companies": ["Example Staffing Group", "Placeholder Outsourcing Ltd"],
            "allowed_companies": ["Acme Robotics"],
            "title_screen_terms": ["java", "php", "sales", "recruiter"],
        },
    }


# -- app -----------------------------------------------------------------------------


def build_app() -> FastAPI:
    """The dashboard router over in-memory fakes. Nothing here can reach Supabase."""
    settings = Settings(
        _env_file=None,  # never read a real .env
        dashboard_password=credential("FAKE_DASHBOARD_PASSWORD", DEFAULT_PASSWORD),
        dashboard_token_secret=credential("FAKE_TOKEN_SECRET", DEFAULT_TOKEN_SECRET),
        dashboard_ingest_key=credential("FAKE_INGEST_KEY", DEFAULT_INGEST_KEY),
    )
    applications = InMemoryApplicationRepository(build_roles())
    runs = InMemoryRunRepository(build_runs())
    rules = InMemoryRulesRepository()
    rules.seed(build_rules())
    attempts = InMemoryLoginAttemptRepository()

    def refuse_supabase() -> None:
        raise RuntimeError("the offline dev server never talks to Supabase; use the in-memory fakes")

    app = FastAPI(title="Dashboard dev server (fake data, offline)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(dashboard_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_application_repository] = lambda: applications
    app.dependency_overrides[get_search_run_repository] = lambda: runs
    app.dependency_overrides[get_search_rules_repository] = lambda: rules
    app.dependency_overrides[get_login_attempt_repository] = lambda: attempts
    app.dependency_overrides[get_postgrest_client] = refuse_supabase  # safety net for new providers

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "fake-data"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline dashboard API with fake data (never touches Supabase).")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="port to listen on (default: 8001)")
    args = parser.parse_args()

    # Show the documented fake defaults; never echo a value that came from the environment.
    password = credential("FAKE_DASHBOARD_PASSWORD", DEFAULT_PASSWORD)
    ingest_key = credential("FAKE_INGEST_KEY", DEFAULT_INGEST_KEY)
    password_hint = password if password == DEFAULT_PASSWORD else "(from FAKE_DASHBOARD_PASSWORD)"
    ingest_hint = ingest_key if ingest_key == DEFAULT_INGEST_KEY else "(from FAKE_INGEST_KEY)"
    # flush: when stdout is redirected to a log file, the banner should still come before uvicorn's lines
    print(f"Dashboard dev server (FAKE DATA, offline) on http://{args.host}:{args.port}", flush=True)
    print(f"  login:      POST /api/dashboard/auth/login  password={password_hint}", flush=True)
    print(f"  ingest key: X-Ingest-Key: {ingest_hint}", flush=True)
    print(f"  CORS:       {', '.join(FRONTEND_ORIGINS)}", flush=True)
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
