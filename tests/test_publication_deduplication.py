import sqlite3
from pathlib import Path

from app.config import Settings
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.publication_repository import (
    PublicationApprovalRepository,
)


VALID_REQUEST = """
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
            + str(tmp_path / "dedupe.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def prepare(
    orchestrator,
    message_id,
):
    return orchestrator.prepare_from_text(
        VALID_REQUEST,
        source=(
            "max:-73294996749751:"
            + str(message_id or "none")
        ),
        source_chat_id="-73294996749751",
        source_message_id=message_id,
        requested_by="100500",
    )


def test_same_max_message_creates_one_approval(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    first = prepare(
        orchestrator,
        "message-777",
    )

    second = prepare(
        orchestrator,
        "message-777",
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is True

    assert (
        first["approval"]["id"]
        == second["approval"]["id"]
    )

    count = (
        orchestrator.repository.connection.execute(
            """
            SELECT COUNT(*)
            FROM publication_approvals
            """
        ).fetchone()[0]
    )

    assert count == 1


def test_different_messages_create_different_approvals(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    first = prepare(
        orchestrator,
        "message-1",
    )

    second = prepare(
        orchestrator,
        "message-2",
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is False

    assert (
        first["approval"]["id"]
        != second["approval"]["id"]
    )


def test_message_without_id_is_not_deduplicated(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    first = prepare(
        orchestrator,
        None,
    )

    second = prepare(
        orchestrator,
        None,
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is False

    assert (
        first["approval"]["id"]
        != second["approval"]["id"]
    )


def test_existing_database_is_migrated(
    tmp_path,
):
    database_path = (
        tmp_path / "legacy-publication.db"
    )

    connection = sqlite3.connect(
        database_path
    )

    connection.executescript(
        """
        CREATE TABLE publication_approvals (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            processed_by TEXT
        );
        """
    )

    connection.commit()
    connection.close()

    repository = PublicationApprovalRepository(
        "sqlite:///" + str(database_path)
    )

    columns = {
        str(row["name"])
        for row in repository.connection.execute(
            """
            PRAGMA table_info(
                publication_approvals
            )
            """
        ).fetchall()
    }

    assert "source_key" in columns

    indexes = {
        str(row["name"])
        for row in repository.connection.execute(
            """
            PRAGMA index_list(
                publication_approvals
            )
            """
        ).fetchall()
    }

    assert (
        "idx_publication_approvals_source_key"
        in indexes
    )


def test_api_has_duplicate_delivery_guard():
    api_path = (
        Path(__file__).parents[1]
        / "app"
        / "api.py"
    )

    text = api_path.read_text(
        encoding="utf-8"
    )

    duplicate_guard = (
        'if result.get("duplicate"):'
    )

    owner_delivery = (
        '"skipped_duplicate"'
    )

    owner_target = (
        "owner_id = str("
    )

    assert duplicate_guard in text
    assert owner_delivery in text

    assert (
        text.index(duplicate_guard)
        < text.index(
            owner_target,
            text.index(duplicate_guard),
        )
    )
