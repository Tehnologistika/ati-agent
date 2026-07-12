from app.services.max_webhook import (
    approval_buttons,
    extract_max_callback,
    extract_max_message,
    extract_update_type,
    first_update,
    is_my_id_command,
    parse_ati_callback,
)


def test_extract_official_max_message():
    body = {
        "update_type": "message_created",
        "message": {
            "recipient": {
                "chat_id": -12345,
            },
            "sender": {
                "user_id": 777,
                "first_name": "Тимур",
                "last_name": "Артурович",
            },
            "body": {
                "mid": "mid-1",
                "text": "#МОЙID",
            },
        },
    }

    message = extract_max_message(body)

    assert extract_update_type(body) == (
        "message_created"
    )
    assert message["chat_id"] == "-12345"
    assert message["user_id"] == "777"
    assert message["message_id"] == "mid-1"
    assert message["author_name"] == (
        "Тимур Артурович"
    )
    assert message["text"] == "#МОЙID"


def test_extract_official_callback():
    body = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "callback-1",
            "payload": (
                "ati:approve:approval-123"
            ),
            "user": {
                "user_id": 777,
            },
        },
        "message": {
            "recipient": {
                "chat_id": -12345,
            },
            "body": {
                "mid": "mid-2",
            },
        },
    }

    callback = extract_max_callback(body)

    assert callback["callback_id"] == (
        "callback-1"
    )
    assert callback["payload"] == (
        "ati:approve:approval-123"
    )
    assert callback["user_id"] == "777"
    assert callback["chat_id"] == "-12345"
    assert callback["message_id"] == "mid-2"

    assert parse_ati_callback(
        callback["payload"]
    ) == (
        "approve",
        "approval-123",
    )


def test_long_polling_update_wrapper():
    body = {
        "updates": [
            {
                "update_type": (
                    "message_callback"
                ),
                "callback": {
                    "callback_id": "cb-1",
                    "payload": (
                        "ati:reject:approval-9"
                    ),
                    "user": {
                        "user_id": 777,
                    },
                },
            }
        ]
    }

    assert first_update(body)["update_type"] == (
        "message_callback"
    )
    assert extract_update_type(body) == (
        "message_callback"
    )
    assert parse_ati_callback(
        extract_max_callback(body)["payload"]
    ) == (
        "reject",
        "approval-9",
    )


def test_commands_and_approval_buttons():
    assert is_my_id_command("#МОЙID")
    assert is_my_id_command("/my_id")
    assert not is_my_id_command("#ЗАЯВКА")

    buttons = approval_buttons("approval-1")

    assert (
        buttons[0][0]["payload"]
        == "ati:approve:approval-1"
    )
    assert (
        buttons[0][1]["payload"]
        == "ati:reject:approval-1"
    )
