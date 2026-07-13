from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import api as api_module
from app.config import Settings
from app.services.registry_status_api import (
    CLOSED_CLIENT_MESSAGE,
    build_registry_status,
    registry_api_secret_is_valid,
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


def make_http_request(
    secret: str | None = None,
) -> Request:
    headers: list[
        tuple[bytes, bytes]
    ] = []

    if secret is not None:
        headers.append(
            (
                b"x-yarus-pik-secret",
                secret.encode("utf-8"),
            )
        )

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": (
            "/internal/registry/requests/"
            "TL-A-000001"
        ),
        "raw_path": b"",
        "query_string": b"",
        "headers": headers,
        "client": (
            "127.0.0.1",
            50000,
        ),
        "server": (
            "127.0.0.1",
            8095,
        ),
    }

    return Request(scope)


def test_secret_validation():
    assert registry_api_secret_is_valid(
        "secret-777",
        "secret-777",
    )

    assert not registry_api_secret_is_valid(
        "wrong",
        "secret-777",
    )

    assert not registry_api_secret_is_valid(
        None,
        "secret-777",
    )

    assert not registry_api_secret_is_valid(
        "secret-777",
        None,
    )


def create_registry_entry(
    tmp_path: Path,
):
    database_url = (
        "sqlite:///"
        + str(tmp_path / "registry-api.db")
    )

    registry = RequestRegistryRepository(
        database_url
    )

    request = parse_transport_request(
        REQUEST_TEXT,
        source="max:test",
    )

    assert request.is_valid_request is True

    entry, created = registry.create_or_get(
        request=request,
        source_channel="max",
        source_chat_id="-73294996749751",
        source_message_id="source-message",
        author_user_id="navigator-777",
    )

    assert created is True

    return database_url, registry, entry


def test_active_status_allows_ayub(
    tmp_path,
):
    _, registry, entry = (
        create_registry_entry(tmp_path)
    )

    try:
        response = build_registry_status(
            entry
        )

    finally:
        registry.connection.close()

    assert response["request_id"] == (
        "TL-A-000001"
    )

    assert response["status"] == "formed"
    assert response["is_active"] is True

    assert response["reply_policy"] == {
        "may_continue": True,
        "client_message": None,
    }

    assert "request" not in response


def test_closed_status_blocks_ayub(
    tmp_path,
):
    _, registry, entry = (
        create_registry_entry(tmp_path)
    )

    try:
        closed, changed = registry.close(
            entry.request_id,
            actor_id="navigator-777",
            owner_user_id="137319351",
            reason="Перевозчик найден",
            actor_name="Навигатор Тест",
            close_message_id="close-mid",
        )

        assert changed is True

        response = build_registry_status(
            closed
        )

    finally:
        registry.connection.close()

    assert response["status"] == "closed"
    assert response["is_active"] is False
    assert response["ayub_status"] == (
        "inactive"
    )

    assert response["close_reason"] == (
        "Перевозчик найден"
    )

    assert response["reply_policy"] == {
        "may_continue": False,
        "client_message": (
            CLOSED_CLIENT_MESSAGE
        ),
    }


def test_endpoint_disabled_without_secret(
    tmp_path,
    monkeypatch,
):
    settings = Settings(
        _env_file=None,
        registry_api_secret=None,
        database_url=(
            "sqlite:///"
            + str(tmp_path / "disabled.db")
        ),
    )

    monkeypatch.setattr(
        api_module,
        "settings",
        settings,
    )

    with pytest.raises(
        HTTPException,
    ) as error:
        api_module.registry_request_status(
            "TL-A-000001",
            make_http_request(),
        )

    assert error.value.status_code == 503
    assert error.value.detail == (
        "registry_api_disabled"
    )


def test_endpoint_rejects_wrong_secret(
    tmp_path,
    monkeypatch,
):
    settings = Settings(
        _env_file=None,
        registry_api_secret="secret-777",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "forbidden.db")
        ),
    )

    monkeypatch.setattr(
        api_module,
        "settings",
        settings,
    )

    with pytest.raises(
        HTTPException,
    ) as error:
        api_module.registry_request_status(
            "TL-A-000001",
            make_http_request("wrong"),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "forbidden"


def test_endpoint_returns_not_found(
    tmp_path,
    monkeypatch,
):
    settings = Settings(
        _env_file=None,
        registry_api_secret="secret-777",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "missing.db")
        ),
    )

    monkeypatch.setattr(
        api_module,
        "settings",
        settings,
    )

    with pytest.raises(
        HTTPException,
    ) as error:
        api_module.registry_request_status(
            "TL-A-999999",
            make_http_request(
                "secret-777"
            ),
        )

    assert error.value.status_code == 404
    assert error.value.detail == (
        "request_not_found"
    )


def test_endpoint_returns_closed_status(
    tmp_path,
    monkeypatch,
):
    database_url, registry, entry = (
        create_registry_entry(tmp_path)
    )

    try:
        registry.close(
            entry.request_id,
            actor_id="137319351",
            owner_user_id="137319351",
            reason="Закрыто владельцем",
            actor_name="Тимур",
            close_message_id="owner-close",
        )

    finally:
        registry.connection.close()

    settings = Settings(
        _env_file=None,
        registry_api_secret="secret-777",
        database_url=database_url,
    )

    monkeypatch.setattr(
        api_module,
        "settings",
        settings,
    )

    response = (
        api_module.registry_request_status(
            entry.request_id,
            make_http_request(
                "secret-777"
            ),
        )
    )

    assert response["ok"] is True
    assert response["request_id"] == (
        entry.request_id
    )

    assert response["status"] == "closed"
    assert response["is_active"] is False

    assert response[
        "reply_policy"
    ]["may_continue"] is False

    assert response[
        "reply_policy"
    ]["client_message"] == (
        CLOSED_CLIENT_MESSAGE
    )


def test_api_source_does_not_accept_secret_in_url():
    path = (
        Path(__file__).parents[1]
        / "app"
        / "api.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert (
        "/internal/registry/requests/"
        "{request_id}"
        in text
    )

    assert (
        'request.headers.get(\n'
        '        "X-Yarus-Pik-Secret"'
        in text
    )

    assert (
        "/internal/registry/{secret}"
        not in text
    )
