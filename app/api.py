from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.config import get_settings
from app.integrations.max_client import MaxClient
from app.negotiation_orchestrator import (
    NegotiationOrchestrator,
)
from app.orchestrator import Orchestrator
from app.services.max_webhook import (
    extract_max_callback,
    extract_max_message,
    extract_update_type,
    is_my_id_command,
    parse_ati_callback,
)

settings = get_settings()

logging.basicConfig(
    level=getattr(
        logging,
        settings.log_level,
        logging.INFO,
    )
)
logger = logging.getLogger("ati_agent.api")

app = FastAPI(
    title="ATI-Agent",
    version="0.2.0",
)


def _webhook_secret_is_valid(
    path_secret: str,
    request: Request,
) -> bool:
    configured = str(
        settings.max_webhook_secret or ""
    ).strip()

    if not configured:
        return False

    header_secret = str(
        request.headers.get(
            "X-Max-Bot-Api-Secret",
            "",
        )
    ).strip()

    return (
        path_secret == configured
        or header_secret == configured
    )


def _safe_callback_answer(
    client: MaxClient,
    callback_id: str,
    notification: str,
) -> dict[str, Any]:
    if not callback_id:
        return {
            "status": "skipped",
            "reason": "missing_callback_id",
        }

    try:
        return client.answer_callback(
            callback_id,
            notification=notification[:1000],
        )
    except Exception as exc:
        logger.exception(
            "MAX callback answer failed"
        )
        return {
            "status": "exception",
            "message": str(exc),
        }


def _handle_ati_callback(
    callback: dict[str, str],
) -> dict[str, Any]:
    parsed = parse_ati_callback(
        callback["payload"]
    )

    client = MaxClient(settings)

    if parsed is None:
        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            "Неизвестная команда.",
        )
        return {
            "ok": True,
            "handled": False,
            "reason": "unsupported_callback",
            "callback_answer": answer.get("status"),
        }

    action, approval_id = parsed
    actor_id = callback["user_id"]

    try:
        orchestrator = NegotiationOrchestrator(
            settings
        )

        if action == "approve":
            result = orchestrator.approve_and_send(
                approval_id,
                actor_id,
            )

            delivery_status = (
                result.get("delivery", {})
                .get("status")
            )

            if delivery_status == "dry_run":
                notification = (
                    "Подтверждение принято. "
                    "ATI работает в безопасном "
                    "режиме DRY_RUN."
                )
            elif delivery_status == "sent":
                notification = (
                    "Сообщение отправлено в ATI."
                )
            else:
                notification = (
                    "Подтверждение обработано. "
                    f"Статус ATI: {delivery_status}"
                )

        else:
            result = orchestrator.reject_approval(
                approval_id,
                actor_id,
            )
            delivery_status = "rejected"
            notification = "Черновик отклонён."

    except PermissionError:
        logger.warning(
            "MAX approval denied for user_id=%s",
            actor_id,
        )
        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            "Недостаточно прав.",
        )
        return {
            "ok": True,
            "handled": True,
            "authorized": False,
            "action": action,
            "callback_answer": answer.get("status"),
        }

    except RuntimeError as exc:
        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            str(exc),
        )
        return {
            "ok": True,
            "handled": True,
            "authorized": False,
            "action": action,
            "error": str(exc),
            "callback_answer": answer.get("status"),
        }

    except (KeyError, ValueError) as exc:
        logger.warning(
            "MAX callback rejected: %s",
            exc,
        )
        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            "Это подтверждение уже обработано "
            "или не найдено.",
        )
        return {
            "ok": True,
            "handled": True,
            "action": action,
            "error": str(exc),
            "callback_answer": answer.get("status"),
        }

    answer = _safe_callback_answer(
        client,
        callback["callback_id"],
        notification,
    )

    return {
        "ok": True,
        "handled": True,
        "authorized": True,
        "action": action,
        "approval_id": approval_id,
        "result_status": delivery_status,
        "callback_answer": answer.get("status"),
    }


@app.get("/")
def root() -> dict:
    return {
        "service": "ati-agent",
        "status": "ok",
        "version": "0.2.0",
        "dry_run": settings.dry_run,
        "ati_mode": settings.ati_mode,
        "max_owner_configured": bool(
            settings.max_owner_user_id
        ),
        "google_sheets_enabled": (
            settings.google_sheets_enabled
        ),
        "google_sheets_dry_run": (
            settings.google_sheets_dry_run
        ),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/max/{secret}")
async def max_webhook(
    secret: str,
    request: Request,
) -> dict:
    if not settings.max_enabled:
        return {
            "ok": True,
            "skipped": True,
            "reason": "max_disabled",
        }

    if not _webhook_secret_is_valid(
        secret,
        request,
    ):
        raise HTTPException(
            status_code=403,
            detail="forbidden",
        )

    body = await request.json()
    update_type = extract_update_type(body)

    if update_type == "message_callback":
        callback = extract_max_callback(body)

        logger.info(
            "MAX callback received: "
            "user_id=%s payload=%s",
            callback["user_id"],
            callback["payload"],
        )

        return _handle_ati_callback(callback)

    if update_type and update_type != "message_created":
        return {
            "ok": True,
            "skipped": True,
            "reason": "unsupported_update_type",
            "update_type": update_type,
        }

    msg = extract_max_message(body)
    text = msg["text"].strip()

    if not text:
        return {
            "ok": True,
            "skipped": True,
            "reason": "empty_text",
        }

    if is_my_id_command(text):
        client = MaxClient(settings)

        response_text = (
            "Ваш MAX user ID: "
            f"`{msg['user_id']}`\n\n"
            "Этот ID необходимо сохранить "
            "на сервере как "
            "`MAX_OWNER_USER_ID`."
        )

        if msg["chat_id"]:
            send_result = client.send_message(
                response_text,
                chat_id=msg["chat_id"],
            )
        elif msg["user_id"]:
            send_result = client.send_message(
                response_text,
                user_id=msg["user_id"],
            )
        else:
            send_result = {
                "status": "skipped",
                "reason": "missing_target",
            }

        return {
            "ok": True,
            "command": "my_id",
            "user_id": msg["user_id"],
            "chat_id": msg["chat_id"],
            "send_status": send_result.get(
                "status"
            ),
        }

    leads_ids = {
        str(value).strip()
        for value in [
            settings.max_leads_chat_id,
            settings.max_navigators_chat_id,
        ]
        if str(value or "").strip()
    }

    if (
        leads_ids
        and msg["chat_id"] not in leads_ids
    ):
        logger.info(
            "MAX message skipped: "
            "chat_id=%s not in leads_ids=%s",
            msg["chat_id"],
            leads_ids,
        )
        return {
            "ok": True,
            "skipped": True,
            "reason": "not_leads_chat",
            "chat_id": msg["chat_id"],
        }

    orchestrator = Orchestrator(settings)

    source = (
        f"max:{msg['chat_id']}:"
        f"{msg['message_id'] or 'no_message_id'}"
    )

    result = orchestrator.process_text_request(
        text,
        source=source,
    )

    logger.info(
        "MAX lead processed: "
        "chat_id=%s message_id=%s valid=%s",
        msg["chat_id"],
        msg["message_id"],
        result.get(
            "request",
            {},
        ).get("is_valid_request"),
    )

    return {
        "ok": True,
        "chat_id": msg["chat_id"],
        "message_id": msg["message_id"],
        "valid": result.get(
            "request",
            {},
        ).get("is_valid_request"),
        "missing_fields": result.get(
            "request",
            {},
        ).get("missing_fields"),
        "sheets_result": result.get(
            "sheets_result"
        ),
        "publication_result": result.get(
            "publication_result"
        ),
    }
