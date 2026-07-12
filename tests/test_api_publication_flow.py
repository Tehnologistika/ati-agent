from __future__ import annotations

import asyncio
from typing import Any

import app.api as api
from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.services.publication_repository import (
    PublicationApprovalRepository,
)


OWNER_ID = "137319351"
SOURCE_CHAT_ID = "100"
AUTHOR_ID = "200"
WEBHOOK_SECRET = "publication-test-secret"


FULL_REQUEST = """
#ЗАЯВКА
Маршрут: Владивосток — Москва
Авто: Toyota Camry
Дата готовности: 15 июля
Состояние: На ходу
Оплата: Наличные
Комментарий: Сквозной тест webhook
""".strip()


class FakeRequest:
    """
    Minimal request object required by max_webhook.

    This avoids FastAPI/Starlette TestClient and therefore
    does not require httpx or httpx2.
    """

    def __init__(
        self,
        body: dict[str, Any],
        *,
        secret: str = WEBHOOK_SECRET,
    ):
        self._body = body
        self.headers = {
            "X-Max-Bot-Api-Secret": secret,
        }

    async def json(self) -> dict[str, Any]:
        return self._body


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        dry_run=True,
        ati_mode="READ_ONLY",
        max_enabled=True,
        max_webhook_secret=WEBHOOK_SECRET,
        max_owner_user_id=OWNER_ID,
        max_leads_chat_id=SOURCE_CHAT_ID,
        max_navigators_chat_id=None,
        database_url=(
            "sqlite:///"
            + str(tmp_path / "api-publication.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
        google_sheets_enabled=False,
    )


def _message_body(
    text: str,
    *,
    message_id: str,
) -> dict[str, Any]:
    return {
        "update_type": "message_created",
        "message": {
            "recipient": {
                "chat_id": int(SOURCE_CHAT_ID),
            },
            "sender": {
                "user_id": int(AUTHOR_ID),
                "first_name": "Навигатор",
            },
            "body": {
                "mid": message_id,
                "text": text,
            },
        },
    }


def _callback_body(
    approval_id: str,
) -> dict[str, Any]:
    return {
        "update_type": "message_callback",
        "callback": {
            "callback_id": (
                "callback-publication-1"
            ),
            "payload": (
                "publication:approve:"
                f"{approval_id}"
            ),
            "user": {
                "user_id": int(OWNER_ID),
            },
        },
        "message": {
            "recipient": {
                "chat_id": int(SOURCE_CHAT_ID),
            },
            "body": {
                "mid": "publication-card-1",
                "text": (
                    "## ЧЕРНОВИК ПУБЛИКАЦИИ В ATI\n\n"
                    "Проверьте данные."
                ),
            },
        },
    }


def _install_fake_max(
    monkeypatch,
) -> tuple[list[dict], list[dict]]:
    sent_messages: list[dict] = []
    callback_answers: list[dict] = []

    def fake_send_message(
        self,
        text,
        *,
        chat_id=None,
        user_id=None,
        buttons=None,
        text_format="markdown",
        notify=True,
    ):
        sent_messages.append(
            {
                "text": text,
                "chat_id": chat_id,
                "user_id": user_id,
                "buttons": buttons,
                "text_format": text_format,
                "notify": notify,
            }
        )

        return {
            "status": "ok",
            "response": {
                "message": {
                    "body": {
                        "mid": (
                            "outgoing-test-message"
                        ),
                    }
                }
            },
        }

    def fake_answer_callback(
        self,
        callback_id,
        *,
        notification=None,
        message=None,
    ):
        callback_answers.append(
            {
                "callback_id": callback_id,
                "notification": notification,
                "message": message,
            }
        )

        return {
            "status": "ok",
            "response": {
                "success": True,
            },
        }

    monkeypatch.setattr(
        api.MaxClient,
        "send_message",
        fake_send_message,
    )

    monkeypatch.setattr(
        api.MaxClient,
        "answer_callback",
        fake_answer_callback,
    )

    return sent_messages, callback_answers


def _call_webhook(
    body: dict[str, Any],
) -> dict[str, Any]:
    """
    Invoke the real async webhook function without
    opening a network socket.
    """

    request = FakeRequest(body)

    return asyncio.run(
        api.max_webhook(
            "callback",
            request,
        )
    )


def test_full_publication_request_goes_to_owner(
    tmp_path,
    monkeypatch,
):
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        api,
        "settings",
        settings,
    )

    sent, _ = _install_fake_max(monkeypatch)

    data = _call_webhook(
        _message_body(
            FULL_REQUEST,
            message_id="full-request-1",
        )
    )

    assert data["ok"] is True
    assert data["publication_request"] is True
    assert data["valid"] is True
    assert data["owner_delivery"] == "ok"

    approval_id = data["approval_id"]

    assert approval_id.startswith(
        "publication-"
    )

    assert len(sent) == 1
    assert str(sent[0]["user_id"]) == OWNER_ID
    assert sent[0]["chat_id"] is None
    assert sent[0]["buttons"] is not None

    assert "ЧЕРНОВИК ПУБЛИКАЦИИ" in (
        sent[0]["text"]
    )

    approve_payload = (
        sent[0]["buttons"][0][0]["payload"]
    )

    assert approve_payload == (
        "publication:approve:"
        + approval_id
    )


def test_incomplete_publication_request_replies_to_chat(
    tmp_path,
    monkeypatch,
):
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        api,
        "settings",
        settings,
    )

    sent, _ = _install_fake_max(monkeypatch)

    data = _call_webhook(
        _message_body(
            "#ЗАЯВКА\nАвто: Toyota Camry",
            message_id="incomplete-request-1",
        )
    )

    assert data["ok"] is True
    assert data["publication_request"] is True
    assert data["valid"] is False

    assert set(data["missing_fields"]) == {
        "origin",
        "destination",
    }

    assert data["response_status"] == "ok"

    assert len(sent) == 1
    assert str(sent[0]["chat_id"]) == (
        SOURCE_CHAT_ID
    )
    assert sent[0]["user_id"] is None

    assert "город загрузки" in sent[0]["text"]
    assert "город выгрузки" in sent[0]["text"]


def test_owner_callback_consumes_publication_in_dry_run(
    tmp_path,
    monkeypatch,
):
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        api,
        "settings",
        settings,
    )

    sent, callback_answers = (
        _install_fake_max(monkeypatch)
    )

    prepared = _call_webhook(
        _message_body(
            FULL_REQUEST,
            message_id="approve-request-1",
        )
    )

    approval_id = prepared["approval_id"]

    data = _call_webhook(
        _callback_body(approval_id)
    )

    assert data["ok"] is True
    assert data["handled"] is True
    assert data["authorized"] is True
    assert data["action"] == "approve"
    assert data["approval_id"] == approval_id
    assert data["result_status"] == "dry_run"

    assert len(sent) == 1
    assert len(callback_answers) == 1

    answer = callback_answers[0]

    assert answer["callback_id"] == (
        "callback-publication-1"
    )

    assert "DRY_RUN" in answer["notification"]
    assert answer["message"] is not None
    assert "Статус" in answer["message"]["text"]
    assert "DRY_RUN" in answer["message"]["text"]

    stored = PublicationApprovalRepository(
        settings.database_url
    ).get(approval_id)

    assert stored.status == (
        PublicationApprovalStatus.CONSUMED
    )
    assert stored.processed_by == OWNER_ID

    assert (
        stored.publication_result["status"]
        == "dry_run"
    )
