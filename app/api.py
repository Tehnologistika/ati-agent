from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.config import get_settings
from app.orchestrator import Orchestrator

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger("ati_agent.api")

app = FastAPI(title="ATI-Agent", version="0.1.0")


def _extract_max_message(body: dict[str, Any]) -> dict[str, str]:
    """Аккуратно достаём chat_id, message_id, user_id, author_name и text из разных форматов MAX webhook."""

    message = body.get("message") or body.get("message_created") or body.get("payload") or body

    chat = message.get("chat") or {}
    sender = message.get("sender") or message.get("from") or message.get("user") or {}

    chat_id = (
        message.get("chat_id")
        or chat.get("id")
        or body.get("chat_id")
        or body.get("chatId")
        or ""
    )

    message_id = (
        message.get("message_id")
        or message.get("id")
        or body.get("message_id")
        or body.get("messageId")
        or ""
    )

    user_id = (
        sender.get("id")
        or message.get("user_id")
        or body.get("user_id")
        or body.get("userId")
        or ""
    )

    author_name = (
        sender.get("name")
        or sender.get("username")
        or sender.get("first_name")
        or message.get("author_name")
        or body.get("author_name")
        or "MAX user"
    )

    text = (
        message.get("text")
        or body.get("text")
        or message.get("body")
        or ""
    )

    return {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "user_id": str(user_id),
        "author_name": str(author_name),
        "text": str(text or ""),
    }


@app.get("/")
def root() -> dict:
    return {
        "service": "ati-agent",
        "status": "ok",
        "dry_run": settings.dry_run,
        "ati_mode": settings.ati_mode,
        "google_sheets_enabled": settings.google_sheets_enabled,
        "google_sheets_dry_run": settings.google_sheets_dry_run,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/max/{secret}")
async def max_webhook(secret: str, request: Request) -> dict:
    if not settings.max_enabled:
        return {"ok": True, "skipped": True, "reason": "max_disabled"}

    if not settings.max_webhook_secret or secret != settings.max_webhook_secret:
        raise HTTPException(status_code=403, detail="forbidden")

    body = await request.json()
    msg = _extract_max_message(body)

    leads_ids = {
        str(x).strip()
        for x in [
            settings.max_leads_chat_id,
            settings.max_navigators_chat_id,
        ]
        if str(x or "").strip()
    }

    if leads_ids and msg["chat_id"] not in leads_ids:
        logger.info("MAX message skipped: chat_id=%s not in leads_ids=%s", msg["chat_id"], leads_ids)
        return {
            "ok": True,
            "skipped": True,
            "reason": "not_leads_chat",
            "chat_id": msg["chat_id"],
        }

    text = msg["text"].strip()
    if not text:
        return {"ok": True, "skipped": True, "reason": "empty_text"}

    orchestrator = Orchestrator(settings)

    source = f"max:{msg['chat_id']}:{msg['message_id'] or 'no_message_id'}"

    result = orchestrator.process_text_request(
        text,
        source=source,
    )

    logger.info(
        "MAX lead processed: chat_id=%s message_id=%s valid=%s",
        msg["chat_id"],
        msg["message_id"],
        result.get("request", {}).get("is_valid_request"),
    )

    return {
        "ok": True,
        "chat_id": msg["chat_id"],
        "message_id": msg["message_id"],
        "valid": result.get("request", {}).get("is_valid_request"),
        "missing_fields": result.get("request", {}).get("missing_fields"),
        "sheets_result": result.get("sheets_result"),
        "publication_result": result.get("publication_result"),
    }
