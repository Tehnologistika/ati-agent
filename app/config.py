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
    ati_mode: str = "READ_ONLY"
    ati_messenger_send_path: str | None = None
    ati_messenger_messages_path: str | None = None
    ati_messenger_conversation_field: str = "conversationId"
    ati_messenger_text_field: str = "text"
    ati_http_timeout_seconds: int = 20

    anthropic_enabled: bool = False
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_timeout_seconds: int = 45
    anthropic_max_tokens: int = 500

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
