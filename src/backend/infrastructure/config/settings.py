"""
Infrastructure configuration — pydantic-settings.

Sensitive values (API keys) are loaded from .env.
Non-sensitive defaults (avatar_id, mode, quality) are declared
here as class attributes so they live in version-controlled code
and can be adjusted without touching .env.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Sensitive (loaded from .env) ─────────────────────────────────────────
    # Numbered keys support round-robin fallback when a key hits its session quota.
    # Define at least LIVEAVATAR_API_KEY_1 in .env; add _2, _3 … as needed.
    liveavatar_api_key_1: str = ""
    liveavatar_api_key_2: str = ""
    openai_api_key: str = "MISSING_OPENAI_KEY"
    supabase_url: str = ""
    supabase_secret_key: str = ""
    dashboard_password: str = ""
    dashboard_token_secret: str = ""
    dashboard_ingest_key: str = ""

    @property
    def liveavatar_api_keys(self) -> list[str]:
        """Ordered list of non-empty API keys. Raises if none are configured."""
        keys = [k for k in (self.liveavatar_api_key_1, self.liveavatar_api_key_2) if k]
        if not keys:
            raise ValueError(
                "No LiveAvatar API keys configured. "
                "Set LIVEAVATAR_API_KEY_1 (and optionally _2) in .env."
            )
        return keys

    # ── Environment ──────────────────────────────────────────────────────────
    environment: str = "development"  # set to "production" in prod env vars

    # ── CORS ─────────────────────────────────────────────────────────────────
    frontend_host: str = "localhost:5173"

    # ── LiveAvatar non-sensitive config ──────────────────────────────────────
    # These defaults are intentionally NOT in .env — they are configuration,
    # not secrets. Override by subclassing or environment-specific .env files.
    liveavatar_base_url: str = "https://api.liveavatar.com/v1"
    liveavatar_avatar_id: str = "03f8332d-9046-42a1-bff3-3b2309f77b58"
    liveavatar_voice_id: str = "83a26e3f-bcff-4887-80a2-17531c342c9e"
    liveavatar_context_id: str = "158f5d55-2d4f-11f1-8d28-066a7fa2e369"                    # optional: UUID of a Context (system prompt + KB) created via POST /v1/contexts. Empty = omit.
    liveavatar_language: str = "en"
    liveavatar_mode: Literal["FULL", "LITE"] = "FULL"  # FULL = LiveAvatar owns STT/LLM/TTS
    liveavatar_sandbox: bool = True                    # set False in production
    liveavatar_video_quality: Literal["medium", "high"] = "medium"
    liveavatar_max_session_duration: int = 120        # seconds — Set to 120 to avoid long sessions.

    # ── OpenAI Realtime non-sensitive config ───────────────────────────────
    openai_realtime_model: str = "gpt-realtime-2025-08-28"
    openai_realtime_voice: str = "alloy"

    # ── OpenAI TTS non-sensitive config ──────────────────────────────────────
    # OpenAI TTS produces 24 kHz / 16-bit / mono PCM when `response_format="pcm"`,
    # which matches LiveAvatar's `agent.speak` audio requirement exactly.
    openai_tts_model: str = "tts-1"                    # tts-1 (fast/cheap) or tts-1-hd
    openai_tts_voice: str = "alloy"                    # alloy, echo, fable, onyx, nova, shimmer

    # ── Dashboard non-sensitive config ────────────────────────────────────────
    dashboard_token_days: int = 30
    dashboard_max_attempts: int = 10
    dashboard_lock_hours: int = 24

    @property
    def supabase_rest_url(self) -> str:
        return f"{self.supabase_url}/rest/v1"

    @property
    def frontend_origin(self) -> str:
        """CORS allow-origin value, supports http and https prefixes."""
        host = self.frontend_host
        if host.startswith("http"):
            return host
        return f"http://{host}"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call once per process."""
    return Settings()
