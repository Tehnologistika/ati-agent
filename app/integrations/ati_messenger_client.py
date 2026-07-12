from typing import Any

import requests

from app.config import Settings


class AtiMessengerClient:
    """ATI Messenger transport with hard safety gates and configurable API contract."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def send_message(
        self,
        conversation_id: str,
        text: str,
        *,
        approval_consumed: bool,
    ) -> dict[str, Any]:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "ATI message was not sent because DRY_RUN=true",
                "conversation_id": conversation_id,
                "text": text,
            }

        if self.settings.ati_mode.upper() != "APPROVAL_REQUIRED":
            return {
                "status": "blocked",
                "message": "ATI message sending requires ATI_MODE=APPROVAL_REQUIRED",
            }

        if not approval_consumed:
            return {
                "status": "blocked",
                "message": "ATI message sending requires a consumed one-time approval",
            }

        if not self.settings.ati_access_token or not self.settings.ati_messenger_send_path:
            return {
                "status": "configuration_required",
                "message": "ATI access token or messenger send path is not configured",
            }

        path = self.settings.ati_messenger_send_path.format(conversation_id=conversation_id)
        url = f"{self.settings.ati_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        payload = {
            self.settings.ati_messenger_conversation_field: conversation_id,
            self.settings.ati_messenger_text_field: text,
        }
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.ati_access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.settings.ati_http_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json() if response.content else {}
        return {"status": "sent", "response": data}

    def fetch_messages(self, conversation_id: str) -> dict[str, Any]:
        if not self.settings.ati_access_token or not self.settings.ati_messenger_messages_path:
            return {
                "status": "configuration_required",
                "message": "ATI access token or messenger messages path is not configured",
            }

        path = self.settings.ati_messenger_messages_path.format(conversation_id=conversation_id)
        url = f"{self.settings.ati_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.settings.ati_access_token}"},
            timeout=self.settings.ati_http_timeout_seconds,
        )
        response.raise_for_status()
        return {"status": "ok", "response": response.json()}
