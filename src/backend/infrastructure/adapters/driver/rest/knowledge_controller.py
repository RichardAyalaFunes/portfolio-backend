"""
Knowledge library REST controller -- driver adapter (inbound).

The dashboard's /dashboard/knowledge section: the AI-written notes of the Obsidian vault as pages.
Same two auth schemes as the rest of /api/dashboard:
  - Bearer <device token> on every read (the password gate's token, see application.auth).
  - X-Ingest-Key on the two write routes the vault publisher calls.
"""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.application.knowledge.get_index.command import GetKnowledgeIndexCommand
from backend.application.knowledge.get_index.port import IGetKnowledgeIndexUseCase
from backend.application.knowledge.get_page.command import GetKnowledgePageCommand
from backend.application.knowledge.get_page.port import IGetKnowledgePageUseCase
from backend.application.knowledge.prune_pages.command import PruneKnowledgePagesCommand
from backend.application.knowledge.prune_pages.port import IPruneKnowledgePagesUseCase
from backend.application.knowledge.publish_pages.command import PublishKnowledgePagesCommand
from backend.application.knowledge.publish_pages.port import IPublishKnowledgePagesUseCase
from backend.application.knowledge.search.command import SearchKnowledgeCommand
from backend.application.knowledge.search.port import ISearchKnowledgeUseCase
from backend.domain.shared.errors import InvalidValueError, NotFoundError
from backend.infrastructure.adapters.driver.rest.dashboard_controller import CurrentDeviceDep, IngestAuthDep
from backend.infrastructure.config.dependencies import (
    get_knowledge_index_use_case,
    get_knowledge_page_use_case,
    get_prune_knowledge_pages_use_case,
    get_publish_knowledge_pages_use_case,
    get_search_knowledge_use_case,
)

router = APIRouter(prefix="/api/dashboard/knowledge", tags=["knowledge"])


# ── Models ───────────────────────────────────────────────────────────────────


class KnowledgeSummaryModel(BaseModel):
    slug: str
    space: str
    kind: str
    title: str
    group: str
    group_order: int
    order: int
    domain: Optional[str] = None
    summary: str
    read_minutes: int
    tags: list[str]
    aliases: list[str]
    source_updated: Optional[str] = None


class KnowledgeIndexResponseModel(BaseModel):
    pages: list[KnowledgeSummaryModel]


class KnowledgePageModel(KnowledgeSummaryModel):
    links: list[str]
    body: dict[str, Any]
    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    published_at: Optional[str] = None


class BacklinkModel(BaseModel):
    slug: str
    space: str
    kind: str
    title: str
    group: str


class KnowledgePageResponseModel(BaseModel):
    page: KnowledgePageModel
    backlinks: list[BacklinkModel]


class KnowledgeSearchResultModel(BaseModel):
    slug: str
    space: str
    kind: str
    title: str
    group: str
    summary: str
    read_minutes: int
    score: int
    matched_in: str
    snippet: str


class KnowledgeSearchResponseModel(BaseModel):
    query: str
    terms: list[str]
    total: int
    results: list[KnowledgeSearchResultModel]


class PublishKnowledgeRequest(BaseModel):
    pages: list[dict[str, Any]]


class PublishKnowledgeResponseModel(BaseModel):
    upserted: int


class PruneKnowledgeRequest(BaseModel):
    keep: list[str] = Field(default_factory=list)


class PruneKnowledgeResponseModel(BaseModel):
    removed: int


# ── Reads (Bearer) ───────────────────────────────────────────────────────────


@router.get("", response_model=KnowledgeIndexResponseModel, summary="The whole library as summary rows")
async def get_index(
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetKnowledgeIndexUseCase, Depends(get_knowledge_index_use_case)],
) -> KnowledgeIndexResponseModel:
    result = await use_case.execute(GetKnowledgeIndexCommand())
    return KnowledgeIndexResponseModel(pages=[KnowledgeSummaryModel(**row) for row in result.pages])


@router.get("/search", response_model=KnowledgeSearchResponseModel, summary="Word-start search over every page")
async def search(
    _device: CurrentDeviceDep,
    use_case: Annotated[ISearchKnowledgeUseCase, Depends(get_search_knowledge_use_case)],
    q: Annotated[str, Query(min_length=1, max_length=120)],
) -> KnowledgeSearchResponseModel:
    result = await use_case.execute(SearchKnowledgeCommand(query=q))
    return KnowledgeSearchResponseModel(
        query=result.query,
        terms=result.terms,
        total=result.total,
        results=[KnowledgeSearchResultModel(**row) for row in result.results],
    )


@router.get("/pages/{slug:path}", response_model=KnowledgePageResponseModel, summary="One page with its backlinks")
async def get_page(
    slug: str,
    _device: CurrentDeviceDep,
    use_case: Annotated[IGetKnowledgePageUseCase, Depends(get_knowledge_page_use_case)],
) -> KnowledgePageResponseModel:
    try:
        result = await use_case.execute(GetKnowledgePageCommand(slug=slug))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return KnowledgePageResponseModel(
        page=KnowledgePageModel(**result.page),
        backlinks=[BacklinkModel(**row) for row in result.backlinks],
    )


# ── Writes (X-Ingest-Key, called by the vault publisher) ─────────────────────


@router.post("/pages", response_model=PublishKnowledgeResponseModel, dependencies=[IngestAuthDep])
async def publish_pages(
    body: PublishKnowledgeRequest,
    use_case: Annotated[IPublishKnowledgePagesUseCase, Depends(get_publish_knowledge_pages_use_case)],
) -> PublishKnowledgeResponseModel:
    """Upsert a batch of pages by slug. One invalid page rejects the batch with the reason (422)."""
    try:
        result = await use_case.execute(PublishKnowledgePagesCommand(pages=body.pages))
    except InvalidValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PublishKnowledgeResponseModel(upserted=result.upserted)


@router.post("/prune", response_model=PruneKnowledgeResponseModel, dependencies=[IngestAuthDep])
async def prune_pages(
    body: PruneKnowledgeRequest,
    use_case: Annotated[IPruneKnowledgePagesUseCase, Depends(get_prune_knowledge_pages_use_case)],
) -> PruneKnowledgeResponseModel:
    """Remove stored pages that are not in `keep` (what the vault no longer contains)."""
    try:
        result = await use_case.execute(PruneKnowledgePagesCommand(keep=body.keep))
    except InvalidValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PruneKnowledgeResponseModel(removed=result.removed)
