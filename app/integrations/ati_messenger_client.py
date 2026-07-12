from __future__ import annotations

import time
from typing import Any

import requests

from app.config import Settings


class AtiMessengerClient:
    """Official ATI Messenger API client with approval-gated write operations."""

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.settings.ati_api_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.ati_access_token}",
            "Accept": "application/json",
        }

    def _configuration_error(self) -> dict[str, Any] | None:
        if self.settings.ati_access_token:
            return None
        return {
            "status": "configuration_required",
            "message": "ATI_ACCESS_TOKEN is not configured",
        }

    def _write_gate(self, approval_consumed: bool) -> dict[str, Any] | None:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "ATI write operation was skipped because DRY_RUN=true",
            }
        if self.settings.ati_mode.upper() != "APPROVAL_REQUIRED":
            return {
                "status": "blocked",
                "message": "ATI write operation requires ATI_MODE=APPROVAL_REQUIRED",
            }
        if not approval_consumed:
            return {
                "status": "blocked",
                "message": "ATI write operation requires a consumed one-time approval",
            }
        return self._configuration_error()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Execute an ATI request with the documented 429 exponential backoff."""

        max_retries = max(0, self.settings.ati_http_max_retries)
        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    timeout=self.settings.ati_http_timeout_seconds,
                    allow_redirects=True,
                    **kwargs,
                )
            except requests.RequestException:
                if attempt >= max_retries:
                    raise
                time.sleep(0.1 * (2**attempt))
                continue

            if response.status_code != 429 or attempt >= max_retries:
                response.raise_for_status()
                return response

            time.sleep(0.1 * (2**attempt))

        raise RuntimeError("ATI request retry loop exited unexpectedly")

    def create_dialog(
        self,
        partner_ati_id: str,
        *,
        partner_name: str | None = None,
        description: str = "Переговоры с перевозчиком",
        approval_consumed: bool,
    ) -> dict[str, Any]:
        gate = self._write_gate(approval_consumed)
        if gate:
            return {**gate, "partner_ati_id": partner_ati_id}

        payload = {
            "channel_type": "dialog",
            "name": partner_name or partner_ati_id,
            "description": description,
            "ati_id": partner_ati_id,
        }
        response = self._request(
            "POST",
            self.settings.ati_messenger_create_chat_path,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        data = response.json() if response.content else {}
        return {"status": "created", "response": data}

    def list_subscriptions(
        self,
        *,
        chat_type: str = "dialog",
        limit: int = 100,
        before: int | None = None,
        after: int | None = None,
    ) -> dict[str, Any]:
        error = self._configuration_error()
        if error:
            return error

        params: dict[str, Any] = {"type": chat_type, "limit": limit}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after

        response = self._request(
            "GET",
            self.settings.ati_messenger_subscriptions_path,
            headers=self._auth_headers(),
            params=params,
        )
        return {"status": "ok", "response": response.json()}

    def send_message(
        self,
        conversation_id: str,
        text: str,
        *,
        approval_consumed: bool,
    ) -> dict[str, Any]:
        gate = self._write_gate(approval_consumed)
        if gate:
            return {
                **gate,
                "conversation_id": conversation_id,
                "text": text,
            }

        path = self.settings.ati_messenger_send_path.format(chat_id=conversation_id)
        response = self._request(
            "POST",
            path,
            headers=self._auth_headers(),
            # ATI requires multipart/form-data for message sending. Requests creates
            # the boundary automatically when the text part is supplied via files.
            files={"text": (None, text)},
        )
        data = response.json() if response.content else {}
        return {"status": "sent", "response": data}

    def fetch_messages(
        self,
        conversation_id: str,
        *,
        before: int | None = None,
        since: int | None = None,
        num: int = 100,
        with_ts: bool = True,
    ) -> dict[str, Any]:
        error = self._configuration_error()
        if error:
            return error

        path = self.settings.ati_messenger_history_path.format(chat_id=conversation_id)
        params: dict[str, Any] = {"num": num, "with_ts": str(with_ts).lower()}
        if before is not None:
            params["before"] = before
        if since is not None:
            params["since"] = since

        response = self._request(
            "GET",
            path,
            headers=self._auth_headers(),
            params=params,
        )
        return {"status": "ok", "response": response.json()}

    def fetch_unread_count(self) -> dict[str, Any]:
        error = self._configuration_error()
        if error:
            return error

        response = self._request(
            "GET",
            self.settings.ati_messenger_inbox_path,
            headers=self._auth_headers(),
        )
        return {"status": "ok", "response": response.json()}
