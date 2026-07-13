from pathlib import Path

import pytest

from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.data_models.request_registry import (
    RegistryRequestStatus,
)
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.request_parser import (
    parse_transport_request,
)
from app.services.request_registry import (
    RequestRegistryRepository,
)


REQUEST_TEXT = """
#ЗАЯВКА
Владивосток - Москва
Лот
готово к отправке
1 300 000 наличными
""".strip()


def parsed_request():
    request = parse_transport_request(
        REQUEST_TEXT
    )

    assert request.is_valid_request is True
    return request


def repository(tmp_path):
    return RequestRegistryRepository(
        "sqlite:///"
        + str(tmp_path / "registry.db")
    )


def create_entry(
    repo,
    *,
    message_id,
    author="navigator-777",
):
    return repo.create_or_get(
        request=parsed_request(),
        source_channel="max",
        source_chat_id="-73294996749751",
        source_message_id=message_id,
        author_user_id=author,
    )


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
            + str(tmp_path / "orchestrator.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def test_registry_assigns_stable_numbers(
    tmp_path,
):
    repo = repository(tmp_path)

    first, first_created = create_entry(
        repo,
        message_id="message-1",
    )

    second, second_created = create_entry(
        repo,
        message_id="message-2",
    )

    assert first_created is True
    assert second_created is True

    assert first.request_id == "TL-A-000001"
    assert second.request_id == "TL-A-000002"

    assert first.author_user_id == (
        "navigator-777"
    )

    assert first.is_active is True
    assert first.status == (
        RegistryRequestStatus.FORMED
    )


def test_same_source_returns_same_request(
    tmp_path,
):
    repo = repository(tmp_path)

    first, first_created = create_entry(
        repo,
        message_id="same-message",
    )

    second, second_created = create_entry(
        repo,
        message_id="same-message",
    )

    assert first_created is True
    assert second_created is False

    assert (
        first.request_id
        == second.request_id
    )


def test_author_can_close_own_request(
    tmp_path,
):
    repo = repository(tmp_path)

    entry, _ = create_entry(
        repo,
        message_id="author-close",
        author="navigator-100",
    )

    closed, changed = repo.close(
        entry.request_id,
        actor_id="navigator-100",
        owner_user_id="137319351",
        reason="Перевозчик найден",
    )

    assert changed is True
    assert closed.is_active is False

    assert closed.status == (
        RegistryRequestStatus.CLOSED
    )

    assert closed.closed_by == (
        "navigator-100"
    )

    assert closed.close_reason == (
        "Перевозчик найден"
    )

    assert closed.ayub_status == "inactive"


def test_foreign_navigator_cannot_close(
    tmp_path,
):
    repo = repository(tmp_path)

    entry, _ = create_entry(
        repo,
        message_id="foreign-close",
        author="navigator-author",
    )

    with pytest.raises(
        PermissionError,
        match="только Навигатор",
    ):
        repo.close(
            entry.request_id,
            actor_id="navigator-foreign",
            owner_user_id="137319351",
        )

    stored = repo.get(entry.request_id)

    assert stored.is_active is True
    assert stored.closed_at is None


def test_owner_can_close_any_request(
    tmp_path,
):
    repo = repository(tmp_path)

    entry, _ = create_entry(
        repo,
        message_id="owner-close",
        author="navigator-200",
    )

    closed, changed = repo.close(
        entry.request_id,
        actor_id="137319351",
        owner_user_id="137319351",
        reason="Закрыто владельцем",
    )

    assert changed is True
    assert closed.is_active is False
    assert closed.closed_by == "137319351"


def test_repeated_close_is_idempotent(
    tmp_path,
):
    repo = repository(tmp_path)

    entry, _ = create_entry(
        repo,
        message_id="repeated-close",
        author="navigator-300",
    )

    first, first_changed = repo.close(
        entry.request_id,
        actor_id="navigator-300",
        owner_user_id="137319351",
    )

    second, second_changed = repo.close(
        entry.request_id,
        actor_id="navigator-300",
        owner_user_id="137319351",
    )

    assert first_changed is True
    assert second_changed is False

    assert first.request_id == second.request_id

    events = repo.list_events(
        entry.request_id
    )

    assert [
        event.event_type
        for event in events
    ] == [
        "request.created",
        "request.closed",
    ]


def test_published_request_moves_to_closing(
    tmp_path,
):
    repo = repository(tmp_path)

    entry, _ = create_entry(
        repo,
        message_id="ati-closing",
        author="navigator-400",
    )

    entry.ati_status = "published"

    repo.connection.execute(
        """
        UPDATE request_registry
        SET payload = ?
        WHERE request_id = ?
        """,
        (
            entry.model_dump_json(),
            entry.request_id,
        ),
    )

    repo.connection.commit()

    closed, _ = repo.close(
        entry.request_id,
        actor_id="navigator-400",
        owner_user_id="137319351",
    )

    assert closed.ati_status == "closing"


def test_publication_links_registry_request(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        REQUEST_TEXT,
        source=(
            "max:-73294996749751:"
            "registry-integration"
        ),
        source_chat_id="-73294996749751",
        source_message_id=(
            "registry-integration"
        ),
        requested_by="navigator-500",
    )

    registry = prepared["registry_request"]
    approval = prepared["approval"]

    assert registry["request_id"] == (
        "TL-A-000001"
    )

    assert registry["author_user_id"] == (
        "navigator-500"
    )

    assert (
        approval["registry_request_id"]
        == registry["request_id"]
    )


def test_closed_request_blocks_old_publish_button(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        REQUEST_TEXT,
        source=(
            "max:-73294996749751:"
            "closed-before-publish"
        ),
        source_chat_id="-73294996749751",
        source_message_id=(
            "closed-before-publish"
        ),
        requested_by="navigator-600",
    )

    request_id = prepared[
        "registry_request"
    ]["request_id"]

    approval_id = prepared[
        "approval"
    ]["id"]

    orchestrator.registry.close(
        request_id,
        actor_id="navigator-600",
        owner_user_id="137319351",
        reason="Перевозчик найден",
    )

    with pytest.raises(
        RuntimeError,
        match="уже закрыта",
    ):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )

    approval = (
        orchestrator.repository.get(
            approval_id
        )
    )

    assert (
        approval.status
        == PublicationApprovalStatus.PENDING
    )


def test_registry_source_contains_authorization_rule():
    path = (
        Path(__file__).parents[1]
        / "app"
        / "services"
        / "request_registry.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert "is_owner" in text
    assert "is_author" in text

    assert (
        "Навигатор, который её опубликовал"
        in text
    )
