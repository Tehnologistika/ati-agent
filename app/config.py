from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"
    dry_run: bool = True
    log_level: str = "INFO"

    # ATI legacy/current names
    ati_client_id: str | None = None
    ati_client_secret: str | None = None
    ati_access_token: str | None = None
    ati_api_base_url: str = "https://api.ati.su"

    # ATI names from current .env
    ati_api_token: str | None = None
    ati_contact_id: str | None = None
    ati_city_id: str | None = None
    ati_mode: str = "READ_ONLY"

    # MAX legacy/current names
    max_bot_token: str | None = None
    max_webhook_secret: str | None = None
    max_group_chat_id: str | None = None

    # MAX names from current .env
    max_enabled: bool = False
    max_api_base: str = "https://botapi.max.ru"
    max_token: str | None = None
    max_leads_chat_id: str | None = None
    max_navigators_chat_id: str | None = None
    max_drivers_chat_id: str | None = None

    # Google legacy/current names
    gmail_credentials_path: str | None = None
    google_service_account_json: str | None = None
    google_sheets_id: str | None = None

    # Google Sheets via Apps Script Web App
    google_sheets_enabled: bool = False
    google_sheets_dry_run: bool = True
    google_sheets_webapp_url: str | None = None
    google_sheets_secret: str | None = None
    google_sheets_main_sheet: str = "Заявки"
    google_sheets_messages_sheet: str = "История сообщений"

    approval_email: str | None = None
    approval_chat_id: str | None = None

    database_url: str = "sqlite:///./ati_agent.db"
    events_log_path: str = "./data/events.jsonl"


def get_settings() -> Settings:
    return Settings()
