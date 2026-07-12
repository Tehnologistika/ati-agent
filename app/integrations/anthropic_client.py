from typing import Any

import requests

from app.config import Settings


class AnthropicClient:
    """Small Claude Messages API client with an explicit opt-in switch."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.anthropic_enabled
            and self.settings.anthropic_api_key
            and self.settings.anthropic_model
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str | None:
        if not self.enabled:
            return None

        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.anthropic_model,
            "max_tokens": self.settings.anthropic_max_tokens,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = requests.post(
            self.settings.anthropic_api_url,
            headers=headers,
            json=payload,
            timeout=self.settings.anthropic_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("content") or []
        text = "".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()
        return text or None
