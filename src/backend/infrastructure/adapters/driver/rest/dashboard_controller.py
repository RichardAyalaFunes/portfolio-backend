"""
Dashboard REST controller -- driver adapter (inbound).

Two auth schemes on this router:
  - Bearer <device token> (HS256, see application.auth) on every /api/dashboard/*
    route except /auth/login.
  - X-Ingest-Key on the routes the CLI scripts call (ingest.js,
    apply-liveness.js, annotate.js, enrich, run metadata upload, and the
    job-search agent's skill-match and search-rules publishing) -- a script isn't
    a "device" and doesn't go through the password gate.
"""

from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.application.applications.annotate.command import AnnotateCommand, AnnotateItem
from backend.application.applications.annotate.port import IAnnotateUseCase
from backend.application.applications.apply_liveness.command import ApplyLivenessCommand
from backend.application.applications.apply_liveness.port import IApplyLivenessUseCase
from backend.application.applications.archive_application.command import ArchiveApplicationCommand
from backend.application.applications.archive_application.port import IArchiveApplicationUseCase
from backend.application.applications.attach_skill_match.command import (
    AttachSkillMatchCommand,
    AttachSkillMatchItem,
)
from backend.application.applications.attach_skill_match.port import IAttachSkillMatchUseCase
from backend.application.applications.create_application.command import CreateApplicationCommand
from backend.application.applications.create_application.port import ICreateApplicationUseCase
from backend.application.applications.enrich_role.command import EnrichRoleCommand, EnrichRoleItem
from backend.application.applications.enrich_role.port import IEnrichRoleUseCase
from backend.application.applications.errors import DuplicateApplicationError
from backend.application.applications.get_application.command import GetApplicationCommand
from backend.application.applications.get_application.port import IGetApplicationUseCase
from backend.application.applications.get_feedback.command import GetFeedbackCommand
from backend.application.applications.get_feedback.port import IGetFeedbackUseCase
from backend.application.applications.get_metrics.command import GetMetricsCommand
from backend.application.applications.get_metrics.port import IGetMetricsUseCase
from backend.application.applications.get_rules.command import GetRulesCommand
from backend.application.applications.get_rules.port import IGetRulesUseCase
from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.port import IIngestBatchUseCase
from backend.application.applications.list_applications.command import ListApplicationsCommand
from backend.application.applications.list_applications.port import IListApplicationsUseCase
from backend.application.applications.ports.search_run_repository import ISearchRunRepository
from backend.application.applications.publish_rules.command import PublishRulesCommand
from backend.application.applications.publish_rules.port import IPublishRulesUseCase
from backend.application.applications.update_application.command import UpdateApplicationCommand
from backend.application.applications.update_application.port import IUpdateApplicationUseCase
from backend.application.applications.update_contact_stage.command import UpdateContactStageCommand
from backend.application.applications.update_contact_stage.port import IUpdateContactStageUseCase
from backend.application.auth.errors import AccountLockedError, InvalidPasswordError, InvalidTokenError
from backend.application.auth.login.command import LoginCommand
from backend.application.auth.login.port import ILoginUseCase
from backend.application.auth.verify_token.command import VerifyTokenCommand
from backend.application.auth.verify_token.port import IVerifyTokenUseCase
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.shared.errors import InvalidValueError, NotFoundError
from backend.infrastructure.config.dependencies import (
    SettingsDep,
    get_annotate_use_case,
    get_apply_liveness_use_case,
    get_archive_application_use_case,
    get_attach_skill_match_use_case,
    get_create_application_use_case,
    get_enrich_role_use_case,
    get_feedback_use_case,
    get_get_application_use_case,
    get_get_rules_use_case,
    get_ingest_batch_use_case,
    get_list_applications_use_case,
    get_login_use_case,
    get_metrics_use_case,
    get_publish_rules_use_case,
    get_search_run_repository,
    get_update_application_use_case,
    get_update_contact_stage_use_case,
    get_verify_token_use_case,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ── Request / response models ────────────────────────────────────────────────


class LoginRequest(BaseModel):
    password: str
    device_id: str = Field(min_length=1)


class LoginResponseModel(BaseModel):
    token: str
    expires_at: datetime


class MeResponse(BaseModel):
    device_id: str


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    legacy_id: Optional[str] = None
    identity_key: str
    title: str
    company: str
    group: Optional[str] = None
    score: Optional[int] = None
    band: Optional[str] = None
    status: str
    application_stage: str
    location_text: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    salary_text: Optional[str] = None
    posted_date: Optional[date] = None
    posted_date_source: Optional[str] = None
    posted_relative: Optional[str] = None
    eligibility_text: Optional[str] = None
    requirements_excerpt: Optional[str] = None
    why_apply: Optional[str] = None
    why_not: Optional[str] = None
    considerations: Optional[str] = None
    jd_url: Optional[str] = None
    source: Optional[str] = None
    found_by_query: Optional[str] = None
    run_date: Optional[date] = None
    first_seen: Optional[date] = None
    last_seen: Optional[date] = None
    live_state: Optional[str] = None
    live_checked_at: Optional[date] = None
    work_remote_allowed: Optional[bool] = None
    drop_stage: Optional[str] = None
    drop_reason: Optional[str] = None
    notes: str = ""
    notes_updated_at: Optional[date] = None
    postings: list[dict[str, Any]] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    application_form: dict[str, Any] = Field(default_factory=dict)
    skill_match: dict[str, Any] = Field(default_factory=dict)
    secondary_lanes: list[str] = Field(default_factory=list)
    discovery_queries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    reviewed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> str:
        return str(value)


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationResponse]


class CreateApplicationRequest(BaseModel):
    title: str
    company: str
    group: Optional[str] = None
    jd_url: Optional[str] = None
    status: str = "To validate"


class UpdateApplicationRequest(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    jd_url: Optional[str] = None


class UpdateContactStageRequest(BaseModel):
    stage: str


class ArchiveResponse(BaseModel):
    application_id: str
    archived: bool = True


class MetricsResponseModel(BaseModel):
    total: int
    status_counts: dict[str, int]
    stage_counts: dict[str, int]
    funnel_by_group: dict[str, dict[str, int]]
    drop_reasons: dict[str, int]
    portal_yield: dict[str, dict[str, int]]


class RunResponse(BaseModel):
    run_date: str
    label: Optional[str] = None
    approx: Optional[bool] = None
    searches_run: Optional[int] = None
    cards_surfaced: Optional[int] = None
    cards_opened: Optional[int] = None
    jd_extracted: Optional[int] = None
    card_screens: dict[str, Any] = Field(default_factory=dict)
    portals: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    validated_account: Optional[str] = None
    browser_surface: Optional[str] = None
    outcome: dict[str, Any] = Field(default_factory=dict)
    line_yield: list[dict[str, Any]] = Field(default_factory=list)
    plan_changes: list[dict[str, Any]] = Field(default_factory=list)


class RunListResponse(BaseModel):
    runs: list[RunResponse]


class FeedbackResponseModel(BaseModel):
    since: date
    since_source: str
    reviewed: list[dict[str, Any]]
    summary: dict[str, Any]
    query_performance: dict[str, dict[str, int]]
    disagreements: dict[str, list[dict[str, Any]]]
    backlog: dict[str, int]
    recent_runs: list[dict[str, Any]]


class IngestRequest(BaseModel):
    roles: list[dict[str, Any]]
    replace: bool = False


class IngestResponseModel(BaseModel):
    added: int
    updated: int
    reposts: int
    total: int
    near_hits: list[dict[str, Any]]


class LivenessRequest(BaseModel):
    sweep: dict[str, dict[str, Any]]


class LivenessResponseModel(BaseModel):
    matched: int
    retired: int
    work_mode_corrected: int
    jd_url_corrected: int
    unmatched: list[str]
    approved_died: list[str]


class AnnotateRequestItem(BaseModel):
    url: str
    note: str


class AnnotateRequest(BaseModel):
    items: list[AnnotateRequestItem]


class AnnotateResponseModel(BaseModel):
    added: int
    already_present: int
    unmatched: list[str]


class EnrichRequestItem(BaseModel):
    application_id: Optional[str] = None
    jd_url: Optional[str] = None
    contacts: Optional[list[dict[str, Any]]] = None
    application_form: Optional[dict[str, Any]] = None


class EnrichRequest(BaseModel):
    items: list[EnrichRequestItem]


class EnrichResponseModel(BaseModel):
    matched: int
    updated: int
    unmatched: list[str]


class SkillMatchRequestItem(BaseModel):
    application_id: Optional[str] = None
    jd_url: Optional[str] = None
    # Required but nullable: an explicit null (or {}) clears the role's table, while a
    # missing key is a 422 -- an item that forgot its payload must not wipe a table.
    skill_match: Optional[dict[str, Any]]


class SkillMatchRequest(BaseModel):
    items: list[SkillMatchRequestItem]


class SkillMatchResponseModel(BaseModel):
    matched: int
    updated: int
    unmatched: list[str]
    invalid: list[str]


class PublishRulesRequest(BaseModel):
    rules: dict[str, Any]


class PublishRulesResponseModel(BaseModel):
    published_at: str
    lanes: int
    lines: int


class RulesResponseModel(BaseModel):
    published_at: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    line_stats: dict[str, dict[str, int]]
    lane_stats: dict[str, dict[str, int]]


def _to_response(application: JobApplication, *, light_skill_match: bool = False) -> ApplicationResponse:
    """`light_skill_match` drops the per-requirement rows from the skill match, keeping
    its header and summary: the list endpoint is already large and its cards only need
    the counters; the detail view fetches the whole table."""
    response = ApplicationResponse.model_validate(application)
    if light_skill_match and response.skill_match:
        response.skill_match = {key: value for key, value in response.skill_match.items() if key != "rows"}
    return response


# ── Auth dependencies ─────────────────────────────────────────────────────────


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_current_device(
    request: Request,
    verify_token_use_case: Annotated[IVerifyTokenUseCase, Depends(get_verify_token_use_case)],
    authorization: Annotated[Optional[str], Header()] = None,
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("bearer "):].strip()
    try:
        result = await verify_token_use_case.execute(VerifyTokenCommand(token=token))
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return result.device_id


CurrentDeviceDep = Annotated[str, Depends(get_current_device)]


async def verify_ingest_key(
    settings: SettingsDep,
    x_ingest_key: Annotated[Optional[str], Header()] = None,
) -> None:
    if not x_ingest_key or x_ingest_key != settings.dashboard_ingest_key:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Ingest-Key")


IngestAuthDep = Depends(verify_ingest_key)


# ── Auth endpoints ────────────────────────────────────────────────────────────


@router.post("/auth/login", response_model=LoginResponseModel, summary="Password gate login")
async def login(
    request: Request,
    body: LoginRequest,
    use_case: Annotated[ILoginUseCase, Depends(get_login_use_case)],
) -> LoginResponseModel:
    try:
        result = await use_case.execute(
            LoginCommand(password=body.password, device_id=body.device_id, ip=_client_ip(request))
        )
    except AccountLockedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except InvalidPasswordError as exc:
        raise HTTPException(status_code=401, detail="Wrong password") from exc
    return LoginResponseModel(token=result.token, expires_at=result.expires_at)


@router.get("/auth/me", response_model=MeResponse, summary="Validate a stored device token")
async def me(device_id: CurrentDeviceDep) -> MeResponse:
    return MeResponse(device_id=device_id)


# ── Application CRUD ──────────────────────────────────────────────────────────


@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    _device: CurrentDeviceDep,
    use_case: Annotated[IListApplicationsUseCase, Depends(get_list_applications_use_case)],
    status: Optional[str] = None,
    stage: Optional[str] = None,
    group: Optional[str] = None,
    source: Optional[str] = None,
    live: Optional[str] = None,
    run: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
) -> ApplicationListResponse:
    result = await use_case.execute(
        ListApplicationsCommand(
            status=status, stage=stage, group=group, source=source,
            live_state=live, run_date=run, query=q, sort=sort,
        )
    )
    return ApplicationListResponse(
        applications=[_to_response(a, light_skill_match=True) for a in result.applications]
    )


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetApplicationUseCase, Depends(get_get_application_use_case)],
) -> ApplicationResponse:
    try:
        result = await use_case.execute(GetApplicationCommand(application_id=application_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(result.application)


@router.post("/applications", response_model=ApplicationResponse, status_code=201)
async def create_application(
    body: CreateApplicationRequest,
    _device: CurrentDeviceDep,
    use_case: Annotated[ICreateApplicationUseCase, Depends(get_create_application_use_case)],
) -> ApplicationResponse:
    try:
        result = await use_case.execute(
            CreateApplicationCommand(
                title=body.title, company=body.company, group=body.group,
                jd_url=body.jd_url, status=body.status,
            )
        )
    except DuplicateApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_response(result.application)


@router.patch("/applications/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    body: UpdateApplicationRequest,
    _device: CurrentDeviceDep,
    use_case: Annotated[IUpdateApplicationUseCase, Depends(get_update_application_use_case)],
) -> ApplicationResponse:
    try:
        result = await use_case.execute(
            UpdateApplicationCommand(
                application_id=application_id, status=body.status, stage=body.stage,
                notes=body.notes, jd_url=body.jd_url,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(result.application)


@router.patch("/applications/{application_id}/contacts/{contact_id}", response_model=ApplicationResponse)
async def update_contact_stage(
    application_id: str,
    contact_id: str,
    body: UpdateContactStageRequest,
    _device: CurrentDeviceDep,
    use_case: Annotated[IUpdateContactStageUseCase, Depends(get_update_contact_stage_use_case)],
) -> ApplicationResponse:
    try:
        result = await use_case.execute(
            UpdateContactStageCommand(application_id=application_id, contact_id=contact_id, stage=body.stage)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(result.application)


@router.delete("/applications/{application_id}", response_model=ArchiveResponse)
async def archive_application(
    application_id: str,
    _device: CurrentDeviceDep,
    use_case: Annotated[IArchiveApplicationUseCase, Depends(get_archive_application_use_case)],
) -> ArchiveResponse:
    try:
        result = await use_case.execute(ArchiveApplicationCommand(application_id=application_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ArchiveResponse(application_id=result.application_id)


# ── Metrics + runs ────────────────────────────────────────────────────────────


@router.get("/metrics", response_model=MetricsResponseModel)
async def get_metrics(
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetMetricsUseCase, Depends(get_metrics_use_case)],
    scope: str = "all",
) -> MetricsResponseModel:
    result = await use_case.execute(GetMetricsCommand(scope=scope))
    return MetricsResponseModel(**result.__dict__)


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    _device: CurrentDeviceDep,
    repository: Annotated[ISearchRunRepository, Depends(get_search_run_repository)],
) -> RunListResponse:
    runs = await repository.list_all()
    return RunListResponse(runs=[RunResponse(**run) for run in runs])


@router.get("/feedback", response_model=FeedbackResponseModel, summary="Richard's review feedback since a date")
async def get_feedback(
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetFeedbackUseCase, Depends(get_feedback_use_case)],
    since: Optional[date] = None,
    recent_runs: int = 5,
) -> FeedbackResponseModel:
    """Read by the job-search agent as its first step. `since` defaults to the
    latest recorded run's date, so each run sees what changed since the last one."""
    result = await use_case.execute(GetFeedbackCommand(since=since, recent_runs=recent_runs))
    return FeedbackResponseModel(**result.__dict__)


@router.get("/rules", response_model=RulesResponseModel, summary="Published search rules plus live stats")
async def get_rules(
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetRulesUseCase, Depends(get_get_rules_use_case)],
) -> RulesResponseModel:
    """The rules document the job-search agent last published (null until it does), and
    stats computed from the roles at read time so they never go stale between publishes."""
    result = await use_case.execute(GetRulesCommand())
    return RulesResponseModel(**result.__dict__)


# ── Ingest / liveness / annotate (X-Ingest-Key, called by the CLI scripts) ───


@router.post("/ingest", response_model=IngestResponseModel, dependencies=[IngestAuthDep])
async def ingest(
    body: IngestRequest,
    use_case: Annotated[IIngestBatchUseCase, Depends(get_ingest_batch_use_case)],
) -> IngestResponseModel:
    result = await use_case.execute(IngestBatchCommand(roles=body.roles, replace=body.replace))
    return IngestResponseModel(**result.__dict__)


@router.post("/liveness", response_model=LivenessResponseModel, dependencies=[IngestAuthDep])
async def apply_liveness(
    body: LivenessRequest,
    use_case: Annotated[IApplyLivenessUseCase, Depends(get_apply_liveness_use_case)],
) -> LivenessResponseModel:
    result = await use_case.execute(ApplyLivenessCommand(sweep=body.sweep))
    return LivenessResponseModel(**result.__dict__)


@router.post("/annotate", response_model=AnnotateResponseModel, dependencies=[IngestAuthDep])
async def annotate(
    body: AnnotateRequest,
    use_case: Annotated[IAnnotateUseCase, Depends(get_annotate_use_case)],
) -> AnnotateResponseModel:
    result = await use_case.execute(
        AnnotateCommand(items=[AnnotateItem(url=i.url, note=i.note) for i in body.items])
    )
    return AnnotateResponseModel(**result.__dict__)


@router.post("/enrich", response_model=EnrichResponseModel, dependencies=[IngestAuthDep])
async def enrich_role(
    body: EnrichRequest,
    use_case: Annotated[IEnrichRoleUseCase, Depends(get_enrich_role_use_case)],
) -> EnrichResponseModel:
    result = await use_case.execute(
        EnrichRoleCommand(
            items=[
                EnrichRoleItem(
                    application_id=i.application_id,
                    jd_url=i.jd_url,
                    contacts=i.contacts,
                    application_form=i.application_form,
                )
                for i in body.items
            ]
        )
    )
    return EnrichResponseModel(**result.__dict__)


@router.post("/skill-match", response_model=SkillMatchResponseModel, dependencies=[IngestAuthDep])
async def attach_skill_match(
    body: SkillMatchRequest,
    use_case: Annotated[IAttachSkillMatchUseCase, Depends(get_attach_skill_match_use_case)],
) -> SkillMatchResponseModel:
    """One bad item never fails the batch: unresolvable items come back in `unmatched`,
    items whose payload failed validation in `invalid` ("<identifier>: <reason>")."""
    result = await use_case.execute(
        AttachSkillMatchCommand(
            items=[
                AttachSkillMatchItem(
                    application_id=i.application_id,
                    jd_url=i.jd_url,
                    skill_match=i.skill_match,
                )
                for i in body.items
            ]
        )
    )
    return SkillMatchResponseModel(**result.__dict__)


@router.post("/rules", response_model=PublishRulesResponseModel, dependencies=[IngestAuthDep])
async def publish_rules(
    body: PublishRulesRequest,
    use_case: Annotated[IPublishRulesUseCase, Depends(get_publish_rules_use_case)],
) -> PublishRulesResponseModel:
    try:
        result = await use_case.execute(PublishRulesCommand(content=body.rules))
    except InvalidValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PublishRulesResponseModel(**result.__dict__)


@router.post("/runs", status_code=204, dependencies=[IngestAuthDep])
async def upsert_run(
    run: dict[str, Any],
    repository: Annotated[ISearchRunRepository, Depends(get_search_run_repository)],
) -> None:
    await repository.upsert(run)
