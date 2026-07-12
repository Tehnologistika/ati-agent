from typing import Any

import pytest

from app.config import Settings
from app.integrations.max_client import MaxClient


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
    ):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                **kwargs,
            }
        )
        return self.responses.pop(0)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        max_token="test-token",
        max_api_base="https://platform-api2.max.ru",
    )


def test_get_me_uses_official_endpoint_and_header():
    session = FakeSession(
        [FakeResponse({"user_id": 123, "is_bot": True})]
    )
    client = MaxClient(_settings(), session=session)

    result = client.get_me()

    assert result["status"] == "ok"

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://platform-api2.max.ru/me"
    assert call["headers"]["Authorization"] == "test-token"


def test_send_message_with_callback_buttons():
    session = FakeSession(
        [FakeResponse({"message": {"body": {"text": "Черновик"}}})]
    )
    client = MaxClient(_settings(), session=session)

    result = client.send_message(
        "Черновик ответа",
        chat_id="12345",
        buttons=[
            [
                {
                    "type": "callback",
                    "text": "Отправить",
                    "payload": "ati:approve:approval-1",
                },
                {
                    "type": "callback",
                    "text": "Отклонить",
                    "payload": "ati:reject:approval-1",
                },
            ]
        ],
    )

    assert result["status"] == "ok"

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://platform-api2.max.ru/messages"
    assert call["params"] == {"chat_id": 12345}

    keyboard = call["json"]["attachments"][0]
    assert keyboard["type"] == "inline_keyboard"
    assert (
        keyboard["payload"]["buttons"][0][0]["payload"]
        == "ati:approve:approval-1"
    )


def test_send_message_requires_one_target():
    client = MaxClient(
        _settings(),
        session=FakeSession([]),
    )

    with pytest.raises(ValueError):
        client.send_message("Тест")

    with pytest.raises(ValueError):
        client.send_message(
            "Тест",
            chat_id=1,
            user_id=2,
        )


def test_answer_callback_uses_answers_endpoint():
    session = FakeSession(
        [FakeResponse({"success": True})]
    )
    client = MaxClient(_settings(), session=session)

    result = client.answer_callback(
        "callback-1",
        notification="Подтверждено",
    )

    assert result["status"] == "ok"

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://platform-api2.max.ru/answers"
    assert call["params"] == {"callback_id": "callback-1"}
    assert call["json"]["notification"] == "Подтверждено"


def test_configured_ca_bundle_is_used(tmp_path):
    bundle = tmp_path / "max-ca.pem"
    bundle.write_text("test certificate bundle", encoding="utf-8")

    settings = Settings(
        _env_file=None,
        max_token="test-token",
        max_api_base="https://platform-api2.max.ru",
        max_ca_bundle=str(bundle),
    )

    session = FakeSession(
        [FakeResponse({"user_id": 123})]
    )

    client = MaxClient(settings, session=session)
    result = client.get_me()

    assert result["status"] == "ok"
    assert session.calls[0]["verify"] == str(bundle)


def test_missing_ca_bundle_is_rejected(tmp_path):
    missing = tmp_path / "missing-ca.pem"

    settings = Settings(
        _env_file=None,
        max_token="test-token",
        max_api_base="https://platform-api2.max.ru",
        max_ca_bundle=str(missing),
    )

    client = MaxClient(
        settings,
        session=FakeSession([]),
    )

    with pytest.raises(
        RuntimeError,
        match="MAX CA bundle not found",
    ):
        client.get_me()


def test_answer_callback_updates_message_and_notification():
    session = FakeSession(
        [FakeResponse({"success": True})]
    )
    client = MaxClient(_settings(), session=session)

    result = client.answer_callback(
        "callback-visible-status",
        notification="Черновик отклонён.",
        message={
            "text": "Карточка\n\nСтатус: отклонено",
            "format": "markdown",
        },
    )

    assert result["status"] == "ok"

    call = session.calls[0]

    assert call["params"] == {
        "callback_id": "callback-visible-status",
    }
    assert call["json"]["notification"] == (
        "Черновик отклонён."
    )
    assert call["json"]["message"]["format"] == (
        "markdown"
    )
    assert "Статус: отклонено" in (
        call["json"]["message"]["text"]
    )
