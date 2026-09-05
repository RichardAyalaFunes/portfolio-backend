"""
Dependency injection — composition root.

Long-lived clients (httpx.AsyncClient, AsyncOpenAI, LiveAvatarClient,
OpenAITTSClient) are constructed once by the FastAPI lifespan in
`main.py` and stashed on `app.state`. The provider functions below
read them from the request's app state. Per-request handler classes
(GenerateTokenHandler, SpeakHandler) are cheap and built per call.
"""

from typing import Annotated

from fastapi import Depends, Request
from postgrest import AsyncPostgrestClient

from backend.application.applications.annotate.handler import AnnotateHandler
from backend.application.applications.annotate.port import IAnnotateUseCase
from backend.application.applications.apply_liveness.handler import ApplyLivenessHandler
from backend.application.applications.apply_liveness.port import IApplyLivenessUseCase
from backend.application.applications.archive_application.handler import ArchiveApplicationHandler
from backend.application.applications.archive_application.port import IArchiveApplicationUseCase
from backend.application.applications.create_application.handler import CreateApplicationHandler
from backend.application.applications.create_application.port import ICreateApplicationUseCase
from backend.application.applications.get_application.handler import GetApplicationHandler
from backend.application.applications.get_application.port import IGetApplicationUseCase
from backend.application.applications.get_metrics.handler import GetMetricsHandler
from backend.application.applications.get_metrics.port import IGetMetricsUseCase
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from backend.application.applications.ingest_batch.port import IIngestBatchUseCase
from backend.application.applications.list_applications.handler import ListApplicationsHandler
from backend.application.applications.list_applications.port import IListApplicationsUseCase
from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.ports.search_run_repository import ISearchRunRepository
from backend.application.applications.update_application.handler import UpdateApplicationHandler
from backend.application.applications.update_application.port import IUpdateApplicationUseCase
from backend.application.auth.login.handler import LoginHandler
from backend.application.auth.login.port import ILoginUseCase
from backend.application.auth.ports.login_attempt_repository import ILoginAttemptRepository
from backend.application.auth.verify_token.handler import VerifyTokenHandler
from backend.application.auth.verify_token.port import IVerifyTokenUseCase
from backend.application.avatar.generate_token.handler import GenerateTokenHandler
from backend.application.avatar.generate_token.port import IGenerateTokenUseCase
from backend.application.avatar.speak.handler import SpeakHandler
from backend.application.avatar.speak.port import ISpeakUseCase
from backend.application.realtime.create_session.handler import CreateRealtimeSessionHandler
from backend.application.realtime.create_session.port import ICreateRealtimeSessionUseCase
from backend.infrastructure.adapters.driven.liveavatar.avatar_client import LiveAvatarClient
from backend.infrastructure.adapters.driven.openai.openai_realtime_client import OpenAIRealtimeClient
from backend.infrastructure.adapters.driven.openai.openai_tts_client import OpenAITTSClient
from backend.infrastructure.adapters.driven.supabase.application_repository import (
    SupabaseJobApplicationRepository,
)
from backend.infrastructure.adapters.driven.supabase.login_attempt_repository import (
    SupabaseLoginAttemptRepository,
)
from backend.infrastructure.adapters.driven.supabase.search_run_repository import (
    SupabaseSearchRunRepository,
)
from backend.infrastructure.config.settings import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_liveavatar_client(request: Request) -> LiveAvatarClient:
    """Provide the lifespan-shared LiveAvatarClient driven adapter."""
    return request.app.state.liveavatar_client  # type: ignore[no-any-return]


def get_openai_tts_client(request: Request) -> OpenAITTSClient:
    """Provide the lifespan-shared OpenAI TTS driven adapter."""
    return request.app.state.openai_tts_client  # type: ignore[no-any-return]


LiveAvatarClientDep = Annotated[LiveAvatarClient, Depends(get_liveavatar_client)]
OpenAITTSClientDep = Annotated[OpenAITTSClient, Depends(get_openai_tts_client)]


def get_generate_token_use_case(
    client: LiveAvatarClientDep,
    settings: SettingsDep,
) -> IGenerateTokenUseCase:
    """Wire GenerateTokenHandler with its dependencies."""
    return GenerateTokenHandler(
        avatar_api_client=client,
        default_avatar_id=settings.liveavatar_avatar_id,
        default_voice_id=settings.liveavatar_voice_id,
        default_context_id=settings.liveavatar_context_id,
        default_language=settings.liveavatar_language,
        default_mode=settings.liveavatar_mode,
        default_is_sandbox=settings.liveavatar_sandbox,
    )


def get_speak_use_case(tts: OpenAITTSClientDep) -> ISpeakUseCase:
    """Wire SpeakHandler with the OpenAI TTS adapter."""
    return SpeakHandler(tts_client=tts)


# ── Realtime ─────────────────────────────────────────────────────────────────


def get_openai_realtime_client(request: Request) -> OpenAIRealtimeClient:
    """Provide the lifespan-shared OpenAI Realtime driven adapter."""
    return request.app.state.openai_realtime_client  # type: ignore[no-any-return]


OpenAIRealtimeClientDep = Annotated[OpenAIRealtimeClient, Depends(get_openai_realtime_client)]


def get_create_realtime_session_use_case(
    client: OpenAIRealtimeClientDep,
    settings: SettingsDep,
) -> ICreateRealtimeSessionUseCase:
    """Wire CreateRealtimeSessionHandler with its dependencies."""
    return CreateRealtimeSessionHandler(
        realtime_client=client,
        default_model=settings.openai_realtime_model,
        default_voice=settings.openai_realtime_voice,
    )


# ── Dashboard ────────────────────────────────────────────────────────────────


def get_postgrest_client(request: Request) -> AsyncPostgrestClient:
    """Provide the lifespan-shared PostgREST client (service-role key, server-side only)."""
    return request.app.state.postgrest_client  # type: ignore[no-any-return]


PostgrestClientDep = Annotated[AsyncPostgrestClient, Depends(get_postgrest_client)]


def get_application_repository(client: PostgrestClientDep) -> IJobApplicationRepository:
    return SupabaseJobApplicationRepository(client=client)


def get_search_run_repository(client: PostgrestClientDep) -> ISearchRunRepository:
    return SupabaseSearchRunRepository(client=client)


def get_login_attempt_repository(client: PostgrestClientDep) -> ILoginAttemptRepository:
    return SupabaseLoginAttemptRepository(client=client)


ApplicationRepositoryDep = Annotated[IJobApplicationRepository, Depends(get_application_repository)]
LoginAttemptRepositoryDep = Annotated[ILoginAttemptRepository, Depends(get_login_attempt_repository)]


def get_login_use_case(repository: LoginAttemptRepositoryDep, settings: SettingsDep) -> ILoginUseCase:
    return LoginHandler(
        attempt_repository=repository,
        dashboard_password=settings.dashboard_password,
        token_secret=settings.dashboard_token_secret,
        token_days=settings.dashboard_token_days,
        max_attempts=settings.dashboard_max_attempts,
        lock_hours=settings.dashboard_lock_hours,
    )


def get_verify_token_use_case(settings: SettingsDep) -> IVerifyTokenUseCase:
    return VerifyTokenHandler(token_secret=settings.dashboard_token_secret)


def get_list_applications_use_case(repository: ApplicationRepositoryDep) -> IListApplicationsUseCase:
    return ListApplicationsHandler(repository=repository)


def get_get_application_use_case(repository: ApplicationRepositoryDep) -> IGetApplicationUseCase:
    return GetApplicationHandler(repository=repository)


def get_create_application_use_case(repository: ApplicationRepositoryDep) -> ICreateApplicationUseCase:
    return CreateApplicationHandler(repository=repository)


def get_update_application_use_case(repository: ApplicationRepositoryDep) -> IUpdateApplicationUseCase:
    return UpdateApplicationHandler(repository=repository)


def get_archive_application_use_case(repository: ApplicationRepositoryDep) -> IArchiveApplicationUseCase:
    return ArchiveApplicationHandler(repository=repository)


def get_ingest_batch_use_case(repository: ApplicationRepositoryDep) -> IIngestBatchUseCase:
    return IngestBatchHandler(repository=repository)


def get_apply_liveness_use_case(repository: ApplicationRepositoryDep) -> IApplyLivenessUseCase:
    return ApplyLivenessHandler(repository=repository)


def get_annotate_use_case(repository: ApplicationRepositoryDep) -> IAnnotateUseCase:
    return AnnotateHandler(repository=repository)


def get_metrics_use_case(repository: ApplicationRepositoryDep) -> IGetMetricsUseCase:
    return GetMetricsHandler(repository=repository)
