from pathlib import Path

import pytest

from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.request_close import (
    is_close_command,
    parse_close_command,
    process_max_close,
)


REQUEST_TEXT = """
#ЗАЯВКА
Владивосток - Москва
Лот
готово к отправке
1 300 000 наличными
""".strip()


def settings_for_test(tmp_path):
    return Settings(
        _env_file=None,
        dry_run=True,
        ati_mode="READ_ONLY",
        ati_contact_id="7776989",
        max_enabled=True,
        max_owner_user_id="137319351",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "close.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def prepare_request(
    tmp_path,
    *,
    message_id="original-message",
    author_id="navigator-author",
):
    settings = settings_for_test(tmp_path)

    orchestrator = PublicationOrchestrator(
        settings
    )

    prepared = orchestrator.prepare_from_text(
        REQUEST_TEXT,
        source=(
            "max:-73294996749751:"
            + message_id
        ),
        source_chat_id="-73294996749751",
        source_message_id=message_id,
        requested_by=author_id,
    )

    return settings, orchestrator, prepared


def close_message(
    *,
    actor_id,
    original_message_id="original-message",
    text="#ЗАКРЫТО",
):
    return {
        "chat_id": "-73294996749751",
        "message_id": "close-message",
        "user_id": actor_id,
        "author_name": "Навигатор Тест",
        "text": text,
        "linked_message_id": (
            original_message_id
        ),
        "linked_chat_id": (
            "-73294996749751"
        ),
        "link_type": "reply",
    }


def test_parse_close_commands():
    assert is_close_command("#ЗАКРЫТО")
    assert is_close_command("/закрыто")
    assert not is_close_command("#ЗАЯВКА")

    command = parse_close_command(
        "#ЗАКРЫТО\nПеревозчик найден"
    )

    assert command is not None
    assert command.request_id is None
    assert command.reason == (
        "Перевозчик найден"
    )

    explicit = parse_close_command(
        "#ЗАКРЫТО TL-A-000123 "
        "Перевозчик найден"
    )

    assert explicit is not None
    assert explicit.request_id == (
        "TL-A-000123"
    )
    assert explicit.reason == (
        "Перевозчик найден"
    )

    legacy = parse_close_command(
        "#ЗАКРЫТО №1234"
    )

    assert legacy is not None
    assert legacy.request_id == (
        "TL-A-001234"
    )
    assert legacy.reason is None


def test_author_closes_by_reply(
    tmp_path,
):
    settings, orchestrator, prepared = (
        prepare_request(tmp_path)
    )

    approval_id = prepared[
        "approval"
    ]["id"]

    result = process_max_close(
        database_url=settings.database_url,
        owner_user_id="137319351",
        text=(
            "#ЗАКРЫТО\n"
            "Перевозчик найден"
        ),
        message=close_message(
            actor_id="navigator-author"
        ),
    )

    entry = result["registry_request"]

    assert result["closed_now"] is True

    assert result["reference_type"] == (
        "linked_message"
    )

    assert entry["status"] == "closed"
    assert entry["is_active"] is False
    assert entry["ayub_status"] == "inactive"

    assert entry["closed_by"] == (
        "navigator-author"
    )

    assert entry["closed_by_name"] == (
        "Навигатор Тест"
    )

    assert entry["close_message_id"] == (
        "close-message"
    )

    assert entry["close_reason"] == (
        "Перевозчик найден"
    )

    assert result[
        "cancelled_approval_ids"
    ] == [approval_id]

    assert result["ati_action"] == (
        "pending_cancelled"
    )

    stored_approval = (
        orchestrator.repository.get(
            approval_id
        )
    )

    assert stored_approval.status == (
        PublicationApprovalStatus.CANCELLED
    )

    events = orchestrator.registry.list_events(
        entry["request_id"]
    )

    assert events[-1].details[
        "closed_by_name"
    ] == "Навигатор Тест"

    assert events[-1].details[
        "close_message_id"
    ] == "close-message"


def test_foreign_navigator_cannot_close(
    tmp_path,
):
    settings, orchestrator, prepared = (
        prepare_request(tmp_path)
    )

    request_id = prepared[
        "registry_request"
    ]["request_id"]

    with pytest.raises(
        PermissionError,
        match="только Навигатор",
    ):
        process_max_close(
            database_url=(
                settings.database_url
            ),
            owner_user_id="137319351",
            text="#ЗАКРЫТО",
            message=close_message(
                actor_id="foreign-navigator"
            ),
        )

    entry = orchestrator.registry.get(
        request_id
    )

    assert entry.is_active is True


def test_owner_closes_by_explicit_id(
    tmp_path,
):
    settings, _, prepared = (
        prepare_request(
            tmp_path,
            message_id="owner-original",
            author_id="navigator-other",
        )
    )

    request_id = prepared[
        "registry_request"
    ]["request_id"]

    result = process_max_close(
        database_url=settings.database_url,
        owner_user_id="137319351",
        text=(
            f"#ЗАКРЫТО {request_id} "
            "Закрыто владельцем"
        ),
        message={
            **close_message(
                actor_id="137319351",
                original_message_id="",
            ),
            "linked_message_id": "",
        },
    )

    assert result["closed_now"] is True

    assert result["reference_type"] == (
        "request_id"
    )

    assert result[
        "registry_request"
    ]["closed_by"] == "137319351"


def test_command_without_target_rejected(
    tmp_path,
):
    settings = settings_for_test(tmp_path)

    with pytest.raises(
        ValueError,
        match="Ответьте командой",
    ):
        process_max_close(
            database_url=(
                settings.database_url
            ),
            owner_user_id="137319351",
            text="#ЗАКРЫТО",
            message={
                **close_message(
                    actor_id="137319351",
                    original_message_id="",
                ),
                "linked_message_id": "",
            },
        )


def test_repeated_close_is_idempotent(
    tmp_path,
):
    settings, orchestrator, prepared = (
        prepare_request(tmp_path)
    )

    message = close_message(
        actor_id="navigator-author"
    )

    first = process_max_close(
        database_url=settings.database_url,
        owner_user_id="137319351",
        text="#ЗАКРЫТО",
        message=message,
    )

    second = process_max_close(
        database_url=settings.database_url,
        owner_user_id="137319351",
        text="#ЗАКРЫТО",
        message=message,
    )

    assert first["closed_now"] is True
    assert second["closed_now"] is False

    request_id = prepared[
        "registry_request"
    ]["request_id"]

    events = orchestrator.registry.list_events(
        request_id
    )

    assert [
        event.event_type
        for event in events
    ] == [
        "request.created",
        "request.closed",
    ]


def test_closed_request_blocks_old_button(
    tmp_path,
):
    settings, orchestrator, prepared = (
        prepare_request(tmp_path)
    )

    approval_id = prepared[
        "approval"
    ]["id"]

    process_max_close(
        database_url=settings.database_url,
        owner_user_id="137319351",
        text="#ЗАКРЫТО",
        message=close_message(
            actor_id="navigator-author"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="уже закрыта",
    ):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )


def test_api_handles_close_before_chat_filter():
    path = (
        Path(__file__).parents[1]
        / "app"
        / "api.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    close_position = text.index(
        "if is_close_command(text):"
    )

    chat_filter_position = text.index(
        "leads_ids = {"
    )

    request_position = text.index(
        "if is_publication_request(text):"
    )

    assert (
        close_position
        < chat_filter_position
        < request_position
    )

    assert (
        "**Заявка реестра:**"
        in text
    )
