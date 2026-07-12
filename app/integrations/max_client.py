from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.config import Settings


class MaxClient:
    """Minimal official MAX Bot API client."""

    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
    ):
        self.settings = settings
        self.session = session or requests.Session()

    def _token(self) -> str | None:
        return self.settings.max_bot_token or self.settings.max_token

    def _url(self, path: str) -> str:
        return (
            f"{self.settings.max_api_base.rstrip('/')}/"
            f"{path.lstrip('/')}"
        )

    def _verify(self) -> bool | str:
        """Return the configured application-specific CA bundle."""

        bundle = str(
            self.settings.max_ca_bundle or ""
        ).strip()

        if not bundle:
            return True

        path = Path(bundle)

        if not path.is_file():
            raise RuntimeError(
                f"MAX CA bundle not found: {bundle}"
            )

        return str(path)

    def _headers(self) -> dict[str, str]:
        token = self._token()
        if not token:
            raise RuntimeError("MAX bot token is not configured")

        return {
            "Authorization": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                self._url(path),
                headers=self._headers(),
                timeout=20,
                verify=self._verify(),
                **kwargs,
            )
        except requests.RequestException as exc:
            return {
                "status": "network_error",
                "message": str(exc),
            }

        if response.status_code >= 400:
            return {
                "status": "http_error",
                "status_code": response.status_code,
                "text": response.text,
            }

        if not response.content:
            return {"status": "ok", "response": {}}

        try:
            data = response.json()
        except ValueError:
            return {
                "status": "invalid_json",
                "text": response.text,
            }

        return {
            "status": "ok",
            "response": data,
        }

    def get_me(self) -> dict[str, Any]:
        """Return information about the connected MAX bot."""

        return self._request("GET", "/me")

    def send_message(
        self,
        text: str,
        *,
        chat_id: str | int | None = None,
        user_id: str | int | None = None,
        buttons: list[list[dict[str, Any]]] | None = None,
        text_format: str = "markdown",
        notify: bool = True,
    ) -> dict[str, Any]:
        """Send a text message to one MAX chat or user."""

        if bool(chat_id) == bool(user_id):
            raise ValueError(
                "Exactly one of chat_id or user_id must be provided"
            )

        params: dict[str, Any]
        if chat_id is not None:
            params = {"chat_id": int(chat_id)}
        else:
            params = {"user_id": int(user_id)}

        payload: dict[str, Any] = {
            "text": text[:4000],
            "format": text_format,
            "notify": notify,
        }

        if buttons:
            payload["attachments"] = [
                {
                    "type": "inline_keyboard",
                    "payload": {
                        "buttons": buttons,
                    },
                }
            ]

        return self._request(
            "POST",
            "/messages",
            params=params,
            json=payload,
        )

    def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Acknowledge an inline keyboard callback."""

        payload: dict[str, Any] = {}

        if notification:
            payload["notification"] = notification

        if message:
            payload["message"] = message

        return self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=payload,
        )
