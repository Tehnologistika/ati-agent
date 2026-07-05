from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"
    dry_run: bool = True
    log_level: str = "INFO"

    ati_client_id: str | None = None
    ati_client_secret: str | None = None
    ati_access_token: str | None = None
    ati_api_base_url: str = "https://api.ati.su"

    max_bot_token: str | None = None
    max_webhook_secret: str | None = None
    max_group_chat_id: str | None = None

    gmail_credentials_path: str | None = None
    google_service_account_json: str | None = None
    google_sheets_id: str | None = None

    approval_email: str | None = None
    approval_chat_id: str | None = None

    database_url: str = "sqlite:///./ati_agent.db"


def get_settings() -> Settings:
    return Settings()
