from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    env: str = "development"
    dry_run: bool = True
    log_level: str = "INFO"

    # ATI authorization: legacy and current environment names
    ati_client_id: str | None = None
    ati_client_secret: str | None = None
    ati_access_token: str | None = None
    ati_api_token: str | None = None
    ati_contact_id: str | None = None
    ati_city_id: str | None = None

    ati_api_base_url: str = "https://api.ati.su"
    ati_mode: str = "READ_ONLY"
    ati_http_timeout_seconds: int = 20
    ati_http_max_retries: int = 4

    # Official ATI Messenger endpoints
    ati_messenger_create_chat_path: str = "/messenger/1.1/chats/"
    ati_messenger_subscriptions_path: str = "/messenger/1.2/subscriptions/"
    ati_messenger_send_path: str = "/messenger/1.2/chats/{chat_id}/messages"
    ati_messenger_history_path: str = "/messenger/1.1/chats/{chat_id}/history/"
    ati_messenger_inbox_path: str = "/messenger/1.1/inbox/"

    # ATI geo and paid search services
    ati_geo_autocomplete_path: str = "/gw/gis-dict/v1/autocomplete/suggestions"
    ati_trucks_search_path: str = "/v1.0/trucks/search/by-filter"
    ati_active_carriers_search_path: str = "/v2/dstats/active_firms/search"
    ati_search_demo_mode: bool = True
    ati_default_country_id: int = 1

    # Claude
    anthropic_enabled: bool = False
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_timeout_seconds: int = 45
    anthropic_max_tokens: int = 500

    # MAX: legacy and current environment names
    max_enabled: bool = False
    max_api_base: str = "https://botapi.max.ru"
    max_token: str | None = None
    max_bot_token: str | None = None
    max_webhook_secret: str | None = None

    max_group_chat_id: str | None = None
    max_leads_chat_id: str | None = None
    max_navigators_chat_id: str | None = None
    max_drivers_chat_id: str | None = None

    # Only this MAX user may approve outgoing ATI messages
    max_owner_user_id: str | None = None

    # Google legacy settings
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

    # Approvals
    approval_email: str | None = None
    approval_chat_id: str | None = None

    # Storage and audit
    database_url: str = "sqlite:///./ati_agent.db"
    events_log_path: str = "./data/events.jsonl"

    @model_validator(mode="after")
    def normalize_legacy_environment_names(self) -> "Settings":
        """Keep old and new environment variable names compatible."""

        if not self.ati_access_token and self.ati_api_token:
            self.ati_access_token = self.ati_api_token
        elif not self.ati_api_token and self.ati_access_token:
            self.ati_api_token = self.ati_access_token

        if not self.max_bot_token and self.max_token:
            self.max_bot_token = self.max_token
        elif not self.max_token and self.max_bot_token:
            self.max_token = self.max_bot_token

        return self


def get_settings() -> Settings:
    return Settings()
