from __future__ import annotations

from typing import Any


def first_update(body: dict[str, Any]) -> dict[str, Any]:
    """Support both direct Webhook Update and Long Polling-style wrappers."""

    updates = body.get("updates")

    if (
        isinstance(updates, list)
        and updates
        and isinstance(updates[0], dict)
    ):
        return updates[0]

    return body


def extract_update_type(body: dict[str, Any]) -> str:
    update = first_update(body)

    return str(
        update.get("update_type")
        or update.get("type")
        or ""
    )


def extract_max_message(
    body: dict[str, Any],
) -> dict[str, str]:
    """
    Extract common fields from official and legacy
    MAX message formats.

    For replies and forwarded messages, also return
    the linked source message identifiers.
    """

    update = first_update(body)

    message = (
        update.get("message")
        or update.get("message_created")
        or update.get("payload")
        or update
    )

    if not isinstance(message, dict):
        message = {}

    message_body = message.get("body") or {}

    if not isinstance(message_body, dict):
        message_body = {}

    recipient = message.get("recipient") or {}

    if not isinstance(recipient, dict):
        recipient = {}

    chat = message.get("chat") or {}

    if not isinstance(chat, dict):
        chat = {}

    sender = (
        message.get("sender")
        or message.get("from")
        or message.get("user")
        or update.get("user")
        or {}
    )

    if not isinstance(sender, dict):
        sender = {}

    link = message.get("link") or {}

    if not isinstance(link, dict):
        link = {}

    linked_message = (
        link.get("message")
        or link.get("linked_message")
        or {}
    )

    if not isinstance(linked_message, dict):
        linked_message = {}

    linked_body = (
        linked_message.get("body")
        or {}
    )

    if not isinstance(linked_body, dict):
        linked_body = {}

    linked_recipient = (
        linked_message.get("recipient")
        or {}
    )

    if not isinstance(linked_recipient, dict):
        linked_recipient = {}

    chat_id = (
        recipient.get("chat_id")
        or message.get("chat_id")
        or chat.get("id")
        or update.get("chat_id")
        or body.get("chat_id")
        or body.get("chatId")
        or ""
    )

    message_id = (
        message_body.get("mid")
        or message_body.get("message_id")
        or message.get("message_id")
        or message.get("id")
        or update.get("message_id")
        or body.get("message_id")
        or body.get("messageId")
        or ""
    )

    user_id = (
        sender.get("user_id")
        or sender.get("id")
        or message.get("user_id")
        or update.get("user_id")
        or body.get("user_id")
        or body.get("userId")
        or ""
    )

    first_name = str(
        sender.get("first_name")
        or ""
    ).strip()

    last_name = str(
        sender.get("last_name")
        or ""
    ).strip()

    full_name = " ".join(
        part
        for part in [
            first_name,
            last_name,
        ]
        if part
    )

    author_name = (
        sender.get("name")
        or sender.get("username")
        or full_name
        or message.get("author_name")
        or update.get("author_name")
        or body.get("author_name")
        or "MAX user"
    )

    message_text = (
        message_body.get("text")
        or message.get("text")
        or update.get("text")
        or body.get("text")
        or ""
    )

    linked_message_id = (
        link.get("mid")
        or link.get("message_id")
        or linked_body.get("mid")
        or linked_body.get("message_id")
        or linked_message.get("mid")
        or linked_message.get("message_id")
        or linked_message.get("id")
        or ""
    )

    linked_chat_id = (
        link.get("chat_id")
        or linked_recipient.get("chat_id")
        or ""
    )

    link_type = (
        link.get("type")
        or link.get("link_type")
        or ""
    )

    return {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "user_id": str(user_id),
        "author_name": str(author_name),
        "text": str(message_text or ""),
        "linked_message_id": str(
            linked_message_id
        ),
        "linked_chat_id": str(
            linked_chat_id
        ),
        "link_type": str(link_type),
    }


def extract_max_callback(body: dict[str, Any]) -> dict[str, str]:
    """Extract callback ID, payload and actor from a message_callback update."""

    update = first_update(body)

    callback = update.get("callback") or body.get("callback") or {}
    if not isinstance(callback, dict):
        callback = {}

    message = update.get("message") or {}
    if not isinstance(message, dict):
        message = {}

    message_body = message.get("body") or {}
    if not isinstance(message_body, dict):
        message_body = {}

    recipient = message.get("recipient") or {}
    if not isinstance(recipient, dict):
        recipient = {}

    user = (
        callback.get("user")
        or update.get("user")
        or message.get("sender")
        or {}
    )

    if not isinstance(user, dict):
        user = {}

    callback_id = (
        callback.get("callback_id")
        or update.get("callback_id")
        or body.get("callback_id")
        or ""
    )

    payload = (
        callback.get("payload")
        or update.get("payload")
        or body.get("payload")
        or ""
    )

    user_id = (
        user.get("user_id")
        or user.get("id")
        or callback.get("user_id")
        or update.get("user_id")
        or ""
    )

    chat_id = (
        recipient.get("chat_id")
        or message.get("chat_id")
        or update.get("chat_id")
        or body.get("chat_id")
        or ""
    )

    message_id = (
        message_body.get("mid")
        or message.get("message_id")
        or message.get("id")
        or ""
    )

    message_text = (
        message_body.get("text")
        or message.get("text")
        or ""
    )

    return {
        "callback_id": str(callback_id),
        "payload": str(payload),
        "user_id": str(user_id),
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "message_text": str(message_text or ""),
    }


def parse_ati_callback(payload: str) -> tuple[str, str] | None:
    """Parse ati:approve:<id> or ati:reject:<id> callback payload."""

    parts = str(payload or "").split(":", 2)

    if len(parts) != 3:
        return None

    namespace, action, approval_id = parts

    if namespace != "ati":
        return None

    if action not in {"approve", "reject"}:
        return None

    if not approval_id.strip():
        return None

    return action, approval_id.strip()


def is_my_id_command(text: str) -> bool:
    normalized = (
        str(text or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("_", "")
    )

    return normalized in {
        "#МОЙID",
        "/МОЙID",
        "МОЙID",
        "#MYID",
        "/MYID",
        "MYID",
    }


def approval_buttons(
    approval_id: str,
) -> list[list[dict[str, str]]]:
    """Build owner approval controls for an ATI draft."""

    return [
        [
            {
                "type": "callback",
                "text": "Отправить",
                "payload": f"ati:approve:{approval_id}",
            },
            {
                "type": "callback",
                "text": "Отклонить",
                "payload": f"ati:reject:{approval_id}",
            },
        ]
    ]
