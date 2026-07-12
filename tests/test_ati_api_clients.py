from typing import Any

from app.config import Settings
from app.integrations.ati_messenger_client import AtiMessengerClient
from app.integrations.ati_search_client import AtiSearchClient


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"Unexpected HTTP status in test: {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def _settings(**overrides):
    values = {
        "dry_run": False,
        "ati_mode": "APPROVAL_REQUIRED",
        "ati_access_token": "test-token",
        "ati_http_max_retries": 0,
    }
    values.update(overrides)
    return Settings(**values)


def test_send_message_uses_official_multipart_endpoint():
    session = FakeSession([FakeResponse({"id": "message-1"})])
    client = AtiMessengerClient(_settings(), session=session)

    result = client.send_message("chat-1", "Здравствуйте", approval_consumed=True)

    assert result["status"] == "sent"
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/messenger/1.2/chats/chat-1/messages")
    assert call["files"] == {"text": (None, "Здравствуйте")}
    assert "Content-Type" not in call["headers"]


def test_create_dialog_uses_partner_ati_id():
    session = FakeSession([FakeResponse({"id": "chat-1"})])
    client = AtiMessengerClient(_settings(), session=session)

    result = client.create_dialog(
        "123456.0",
        partner_name="Иван",
        approval_consumed=True,
    )

    assert result["status"] == "created"
    call = session.calls[0]
    assert call["url"].endswith("/messenger/1.1/chats/")
    assert call["json"]["channel_type"] == "dialog"
    assert call["json"]["ati_id"] == "123456.0"


def test_fetch_history_uses_official_endpoint_and_cursor():
    session = FakeSession([FakeResponse([{"id": "message-1", "text": "Ответ"}])])
    client = AtiMessengerClient(_settings(), session=session)

    result = client.fetch_messages("chat-1", since=100, num=50)

    assert result["status"] == "ok"
    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/messenger/1.1/chats/chat-1/history/")
    assert call["params"]["since"] == 100
    assert call["params"]["num"] == 50


def test_resolve_city_selects_exact_city_name():
    session = FakeSession(
        [
            FakeResponse(
                {
                    "suggestions": [
                        {
                            "type": 1,
                            "city": {"id": 3611, "name": "Москва"},
                            "region": {"name": "Москва"},
                            "country": {"name": "Россия"},
                            "address": "Москва, Россия",
                        }
                    ]
                }
            )
        ]
    )
    client = AtiSearchClient(_settings(), session=session)

    result = client.resolve_city("Москва")

    assert result["status"] == "ok"
    assert result["city"]["id"] == 3611
    call = session.calls[0]
    assert call["url"].endswith("/gw/gis-dict/v1/autocomplete/suggestions")
    assert call["json"]["suggestion_types"] == 1


def test_truck_search_builds_read_only_demo_request():
    session = FakeSession([FakeResponse({"total_count": 1, "accounts": {}})])
    client = AtiSearchClient(_settings(ati_search_demo_mode=True), session=session)

    result = client.search_trucks(origin_id=3611, destination_id=125)

    assert result["status"] == "ok"
    call = session.calls[0]
    assert call["url"].endswith("/v1.0/trucks/search/by-filter")
    assert call["params"] == {"demo": "true"}
    assert call["json"]["filter"]["from"]["id"] == 3611
    assert call["json"]["filter"]["to"]["id"] == 125


def test_active_carrier_search_builds_route_request():
    session = FakeSession([FakeResponse({"is_demo": True, "ok": True, "result": []})])
    client = AtiSearchClient(_settings(ati_search_demo_mode=True), session=session)

    result = client.search_active_carriers(origin_id=3611, destination_id=125)

    assert result["status"] == "ok"
    call = session.calls[0]
    assert call["url"].endswith("/v2/dstats/active_firms/search")
    assert call["params"] == {"demo": "true"}
    assert call["json"]["from"] == {"id": 3611, "type": 2}
    assert call["json"]["to"] == {"id": 125, "type": 2}
