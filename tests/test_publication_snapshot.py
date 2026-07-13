from pathlib import Path

import pytest

from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.publication_snapshot import (
    snapshot_hash,
    verify_snapshot,
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
            + str(tmp_path / "snapshot.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def prepare(
    orchestrator,
    message_id="snapshot-message",
):
    return orchestrator.prepare_from_text(
        REQUEST_TEXT,
        source=(
            "max:-73294996749751:"
            + message_id
        ),
        source_chat_id="-73294996749751",
        source_message_id=message_id,
        requested_by="100500",
    )


def test_preview_and_hash_are_saved(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    result = prepare(orchestrator)

    approval = orchestrator.repository.get(
        result["approval"]["id"]
    )

    assert approval.ati_preview is not None
    assert approval.ati_preview_hash

    assert (
        approval.ati_preview_hash
        == snapshot_hash(
            approval.ati_preview
        )
    )

    assert (
        result["ati_preview"]
        == approval.ati_preview
    )


def test_approval_does_not_rebuild_preview(
    tmp_path,
    monkeypatch,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = prepare(
        orchestrator,
        "immutable-message",
    )

    original_snapshot = prepared[
        "ati_preview"
    ]

    def forbidden_rebuild(*args, **kwargs):
        raise AssertionError(
            "Preview must not be rebuilt on approval"
        )

    monkeypatch.setattr(
        "app.publication_orchestrator."
        "build_publication_preview",
        forbidden_rebuild,
    )

    result = (
        orchestrator.approve_and_publish(
            prepared["approval"]["id"],
            "137319351",
        )
    )

    assert (
        result["ati_preview"]
        == original_snapshot
    )

    assert (
        result["publication_result"][
            "ati_preview"
        ]
        == original_snapshot
    )

    assert (
        result["publication_result"]["status"]
        == "dry_run"
    )


def test_modified_snapshot_is_blocked(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = prepare(
        orchestrator,
        "tampered-message",
    )

    approval_id = prepared[
        "approval"
    ]["id"]

    approval = orchestrator.repository.get(
        approval_id
    )

    approval.ati_preview[
        "note"
    ] = "Подменённый текст."

    # Старый hash намеренно сохраняется.
    orchestrator.repository.save(
        approval
    )

    with pytest.raises(
        RuntimeError,
        match="изменён или повреждён",
    ):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )

    stored = orchestrator.repository.get(
        approval_id
    )

    assert (
        stored.status
        == PublicationApprovalStatus.PENDING
    )


def test_legacy_approval_without_snapshot_blocked(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = prepare(
        orchestrator,
        "legacy-message",
    )

    approval_id = prepared[
        "approval"
    ]["id"]

    approval = orchestrator.repository.get(
        approval_id
    )

    approval.ati_preview = None
    approval.ati_preview_hash = None

    orchestrator.repository.save(
        approval
    )

    with pytest.raises(
        RuntimeError,
        match="отсутствует сохранённый снимок",
    ):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )

    stored = orchestrator.repository.get(
        approval_id
    )

    assert (
        stored.status
        == PublicationApprovalStatus.PENDING
    )


def test_duplicate_uses_original_snapshot(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    first = prepare(
        orchestrator,
        "duplicate-snapshot-message",
    )

    original_note = first[
        "ati_preview"
    ]["note"]

    # Изменение настроек после создания approval
    # не должно менять сохранённую карточку.
    orchestrator.settings.ati_contact_id = (
        "9999999"
    )

    second = prepare(
        orchestrator,
        "duplicate-snapshot-message",
    )

    assert second["duplicate"] is True

    assert (
        second["approval"]["id"]
        == first["approval"]["id"]
    )

    assert (
        second["ati_preview"]["note"]
        == original_note
    )

    assert (
        second["ati_preview"]
        == first["ati_preview"]
    )


def test_snapshot_module_rejects_wrong_hash():
    snapshot = {
        "payload": {
            "cargo_application": {
                "external_id": "TL-ATI-TEST"
            }
        },
        "ready_for_api": False,
    }

    with pytest.raises(
        RuntimeError,
        match="изменён или повреждён",
    ):
        verify_snapshot(
            snapshot,
            "0" * 64,
        )


def test_orchestrator_source_has_no_rebuild_after_get():
    path = (
        Path(__file__).parents[1]
        / "app"
        / "publication_orchestrator.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    approval_method = text.split(
        "    def approve_and_publish(",
        1,
    )[1]

    assert (
        "verify_snapshot("
        in approval_method
    )

    assert (
        "build_publication_preview("
        not in approval_method
    )
