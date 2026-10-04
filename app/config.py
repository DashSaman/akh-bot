"""Application configuration (environment-driven). Secrets only via env/.env, never committed."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "production"
    data_dir: str = "./data"
    log_level: str = "INFO"

    admin_username: str = "admin"
    admin_password: str = ""
    admin_password_hash: str = ""
    session_secret: str = ""
    session_ttl_hours: int = 12

    brand_config: str = "config/brand.yml"
    public_base_url: str = ""

    llm_provider: str = "glm"
    glm_api_key: str = ""
    glm_base_url: str = "https://api.z.ai/api/paas/v4"
    glm_model: str = "glm-4.6"
    llm_timeout_seconds: float = 90.0

    telegram_bot_token: str = ""
    telegram_publish_chat_id: str = ""  # REAL public news channel (type=channel, validated)
    telegram_staging_chat_id: str = ""   # optional staging/test chat
    telegram_admin_chat_id: str = ""     # optional owner alerts chat
    newsroom_owner_telegram_id: str = ""    # E3: numeric owner user id
    editorial_bot_intake_enabled: bool = False  # E1: flag OFF by default
    iran_crisis_calm_minutes: int = 60       # A4: auto-exit after calm
    telegram_news_chat_id: str = ""      # legacy alias → publish (being retired)

    max_provisional_posts_per_hour: int = 45
    max_confirmed_posts_per_hour: int = 60
    min_breaking_importance: int = 60
    standard_max_age_minutes: int = 180
    breaking_max_age_minutes: int = 720    # 0..100; below → no provisional publication
    telegram_ingest_api_id: int = 0
    telegram_ingest_api_hash: str = ""
    telegram_ingest_session: str = ""

    workers_enabled: bool = True
    autonomous_mode: bool = True
    global_source_sweep_seconds: int = 120
    verify_recheck_interval_seconds: int = 300
    verifying_deadline_minutes: int = 60
    orphan_raw_item_seconds: int = 120
    media_cleanup_interval_seconds: int = 300
    media_cache_max_mb: int = 512
    disk_critical_percent: int = 85
    max_source_video_mb: int = 50
    event_engine_v2_enabled: bool = False  # P3 kill switch — default OFF
    # P3-D — per-source context + burst aggregation (wired by P3-E; V2 stays off)
    source_context_ttl_seconds: int = 1800   # SOURCE_CONTEXT_TTL_SECONDS
    event_burst_window_seconds: int = 180    # EVENT_BURST_WINDOW_SECONDS
    # P3-E/F — story evolution + materiality/debounce (live behind V2 flag)
    max_public_story_details: int = 5        # MAX_PUBLIC_STORY_DETAILS cap
    edit_debounce_seconds: int = 120         # rapid updates consolidate into one EDIT
    # MEDIA_FALLBACK_CARDS_ENABLED: OFF until the new card renderer passes
    # its 10-fixture visual regression (broken-card owner screenshot).
    media_fallback_cards_enabled: bool = False
    ingest_interval_seconds: int = 300
    pipeline_interval_seconds: int = 60
    jobs_interval_seconds: int = 10
    # STALL-RECOVERY: bounds every job handler so a hung network call
    # retries instead of freezing the whole jobs loop (2026-10-04 incident)
    job_handler_timeout_seconds: int = 180

    max_posts_per_hour: int = 60
    max_posts_per_day: int = 500
    max_llm_calls_per_minute: int = 30
    max_llm_calls_per_hour: int = 500

    @property
    def db_path(self) -> str:
        import os

        return os.path.join(self.data_dir, "akhbot.db")

    @property
    def llm_ready(self) -> bool:
        return bool(self.glm_api_key)

    @property
    def telegram_publish_target(self) -> str:
        """PUBLIC news goes ONLY to the validated publish channel.
        No silent fallback to staging/private chats — an empty target blocks publishing."""
        return self.telegram_publish_chat_id or self.telegram_news_chat_id

    @property
    def telegram_publish_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_publish_target)

    @property
    def telegram_ingest_ready(self) -> bool:
        return bool(self.telegram_ingest_api_id and self.telegram_ingest_api_hash and self.telegram_ingest_session)

    @property
    def preview_mode(self) -> bool:
        """Preview mode: public brand/domain undecided. Site stays unindexed until PUBLIC_BASE_URL set."""
        return not self.public_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
