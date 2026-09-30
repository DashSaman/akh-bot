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
    telegram_staging_chat_id: str = ""
    telegram_ingest_api_id: int = 0
    telegram_ingest_api_hash: str = ""
    telegram_ingest_session: str = ""

    workers_enabled: bool = True
    ingest_interval_seconds: int = 300
    pipeline_interval_seconds: int = 60
    jobs_interval_seconds: int = 10

    max_posts_per_hour: int = 12
    max_posts_per_day: int = 120

    @property
    def db_path(self) -> str:
        import os

        return os.path.join(self.data_dir, "akhbot.db")

    @property
    def llm_ready(self) -> bool:
        return bool(self.glm_api_key)

    @property
    def telegram_publish_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_staging_chat_id)

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
