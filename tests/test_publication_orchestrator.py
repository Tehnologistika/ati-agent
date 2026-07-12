import pytest

from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.publication_orchestrator import (
    PublicationOrchestrator,
)


VALID_REQUEST = """
#ЗАЯВКА
Маршрут: Владивосток — Москва
Авто: Toyota Camry
Дата готовности: 15 июля
Состояние: На ходу
Оплата: Наличные
Комментарий: Технический тест
""".strip()


def _settings(tmp_path):
    return Settings(
        _env_file=None,
        dry_run=True,
        ati_mode="READ_ONLY",
        max_enabled=True,
        max_owner_user_id="137319351",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "publication.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def test_prepare_valid_publication(tmp_path):
    orchestrator = PublicationOrchestrator(
        _settings(tmp_path)
    )

    result = orchestrator.prepare_from_text(
        VALID_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-1",
        requested_by="200",
    )

    assert result["request"]["is_valid_request"]
    assert result["request"]["missing_fields"] == []
    assert result["draft"]["route"] == (
        "Владивосток — Москва"
    )

    approval = result["approval"]

    assert approval is not None
    assert approval["status"] == (
        PublicationApprovalStatus.PENDING
    )


def test_incomplete_request_has_no_approval(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        _settings(tmp_path)
    )

    result = orchestrator.prepare_from_text(
        "#ЗАЯВКА\nАвто: Toyota Camry",
        source="max:test",
        source_chat_id="100",
        source_message_id="message-2",
        requested_by="200",
    )

    assert not result["request"]["is_valid_request"]
    assert set(
        result["request"]["missing_fields"]
    ) == {
        "origin",
        "destination",
    }
    assert result["approval"] is None


def test_owner_approval_is_consumed_in_dry_run(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        _settings(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        VALID_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-3",
        requested_by="200",
    )

    approval_id = prepared["approval"]["id"]

    result = orchestrator.approve_and_publish(
        approval_id,
        "137319351",
    )

    assert (
        result["publication_result"]["status"]
        == "dry_run"
    )

    stored = orchestrator.repository.get(
        approval_id
    )

    assert stored.status == (
        PublicationApprovalStatus.CONSUMED
    )
    assert stored.processed_by == "137319351"

    with pytest.raises(ValueError):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )


def test_non_owner_cannot_approve(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        _settings(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        VALID_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-4",
        requested_by="200",
    )

    approval_id = prepared["approval"]["id"]

    with pytest.raises(PermissionError):
        orchestrator.approve_and_publish(
            approval_id,
            "999999",
        )

    stored = orchestrator.repository.get(
        approval_id
    )

    assert stored.status == (
        PublicationApprovalStatus.PENDING
    )


def test_owner_can_reject_publication(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        _settings(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        VALID_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-5",
        requested_by="200",
    )

    approval_id = prepared["approval"]["id"]

    result = orchestrator.reject(
        approval_id,
        "137319351",
    )

    assert result["status"] == "rejected"

    stored = orchestrator.repository.get(
        approval_id
    )

    assert stored.status == (
        PublicationApprovalStatus.REJECTED
    )
    assert stored.processed_by == "137319351"
