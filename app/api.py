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
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.max_webhook import (
    extract_max_callback,
    extract_max_message,
    extract_update_type,
    is_my_id_command,
    parse_ati_callback,
)
from app.services.publication_max import (
    build_missing_fields_message,
    build_publication_card,
    is_publication_request,
    parse_publication_callback,
    publication_buttons,
)
from app.services.request_close import (
    is_close_command,
    process_max_close,
)
from app.services.registry_status_api import (
    build_registry_status,
    registry_api_secret_is_valid,
)
from app.services.request_registry import (
    RequestRegistryRepository,
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


def _callback_status_message(
    original_text: str,
    status_text: str,
) -> dict[str, Any]:
    """Replace callback buttons with a visible processing status."""

    base = str(original_text or "").strip()

    if not base:
        base = "Результат обработки черновика ATI-Agent"

    suffix = (
        "\n\n---\n"
        f"**Статус:** {status_text.strip()}"
    )

    available = max(0, 4000 - len(suffix))

    return {
        "text": base[:available] + suffix,
        "format": "markdown",
    }


def _safe_callback_answer(
    client: MaxClient,
    callback_id: str,
    notification: str,
    *,
    message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not callback_id:
        return {
            "status": "skipped",
            "reason": "missing_callback_id",
        }

    try:
        result = client.answer_callback(
            callback_id,
            notification=notification[:1000],
            message=message,
        )

        response = result.get("response")
        api_success = (
            response.get("success")
            if isinstance(response, dict)
            else None
        )

        if (
            result.get("status") != "ok"
            or api_success is False
        ):
            logger.warning(
                "MAX callback answer was not successful: %s",
                result,
            )
        else:
            logger.info(
                "MAX callback answer completed: "
                "status=%s api_success=%s",
                result.get("status"),
                api_success,
            )

        return result

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

    updated_message = _callback_status_message(
        callback.get("message_text", ""),
        notification,
    )

    answer = _safe_callback_answer(
        client,
        callback["callback_id"],
        notification,
        message=updated_message,
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


def _handle_publication_callback(
    callback: dict[str, str],
) -> dict[str, Any]:
    """Approve or reject one ATI publication draft."""

    parsed = parse_publication_callback(
        callback["payload"]
    )

    client = MaxClient(settings)

    if parsed is None:
        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            "Неизвестная команда публикации.",
        )

        return {
            "ok": True,
            "handled": False,
            "reason": (
                "unsupported_publication_callback"
            ),
            "callback_answer": answer.get(
                "status"
            ),
        }

    action, approval_id = parsed
    actor_id = callback["user_id"]

    try:
        orchestrator = PublicationOrchestrator(
            settings
        )

        if action == "approve":
            result = (
                orchestrator.approve_and_publish(
                    approval_id,
                    actor_id,
                )
            )

            publication_status = (
                result.get(
                    "publication_result",
                    {},
                ).get("status")
            )

            if publication_status == "dry_run":
                notification = (
                    "Публикация подтверждена. "
                    "ATI работает в безопасном "
                    "режиме DRY_RUN."
                )
            elif publication_status in {
                "published",
                "sent",
            }:
                notification = (
                    "Заявка опубликована в ATI."
                )
            else:
                notification = (
                    "Подтверждение обработано. "
                    "Статус публикации: "
                    f"{publication_status}"
                )

        else:
            result = orchestrator.reject(
                approval_id,
                actor_id,
            )
            publication_status = "rejected"
            notification = (
                "Публикация отклонена."
            )

    except PermissionError:
        logger.warning(
            "MAX publication approval denied "
            "for user_id=%s",
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
            "callback_answer": answer.get(
                "status"
            ),
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
            "callback_answer": answer.get(
                "status"
            ),
        }

    except (KeyError, ValueError) as exc:
        logger.warning(
            "MAX publication callback rejected: %s",
            exc,
        )

        answer = _safe_callback_answer(
            client,
            callback["callback_id"],
            (
                "Эта публикация уже обработана "
                "или не найдена."
            ),
        )

        return {
            "ok": True,
            "handled": True,
            "action": action,
            "error": str(exc),
            "callback_answer": answer.get(
                "status"
            ),
        }

    updated_message = _callback_status_message(
        callback.get("message_text", ""),
        notification,
    )

    answer = _safe_callback_answer(
        client,
        callback["callback_id"],
        notification,
        message=updated_message,
    )

    return {
        "ok": True,
        "handled": True,
        "authorized": True,
        "action": action,
        "approval_id": approval_id,
        "result_status": publication_status,
        "callback_answer": answer.get(
            "status"
        ),
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


@app.get(
    "/internal/registry/requests/{request_id}"
)
def registry_request_status(
    request_id: str,
    request: Request,
) -> dict[str, Any]:
    """
    Read-only status endpoint for Ayub.

    Authentication:
    X-Yarus-Pik-Secret HTTP header.
    """

    configured_secret = str(
        settings.registry_api_secret or ""
    ).strip()

    if not configured_secret:
        raise HTTPException(
            status_code=503,
            detail="registry_api_disabled",
        )

    provided_secret = request.headers.get(
        "X-Yarus-Pik-Secret"
    )

    if not registry_api_secret_is_valid(
        provided_secret,
        configured_secret,
    ):
        raise HTTPException(
            status_code=403,
            detail="forbidden",
        )

    registry = RequestRegistryRepository(
        settings.database_url
    )

    try:
        try:
            entry = registry.get(request_id)

        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="request_not_found",
            ) from exc

        return build_registry_status(entry)

    finally:
        registry.connection.close()


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

        if parse_publication_callback(
            callback["payload"]
        ) is not None:
            return _handle_publication_callback(
                callback
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

    if is_close_command(text):
        client = MaxClient(settings)

        try:
            close_result = process_max_close(
                database_url=(
                    settings.database_url
                ),
                owner_user_id=str(
                    settings.max_owner_user_id
                    or ""
                ),
                text=text,
                message=msg,
            )

            registry_entry = close_result[
                "registry_request"
            ]

            request_id = str(
                registry_entry["request_id"]
            )

            closed_now = bool(
                close_result["closed_now"]
            )

            cancelled_count = len(
                close_result[
                    "cancelled_approval_ids"
                ]
            )

            ati_action = str(
                close_result["ati_action"]
            )

            if (
                ati_action
                == "close_publication_required"
            ):
                ati_text = (
                    "объявление отмечено для "
                    "снятия с публикации"
                )

            elif cancelled_count:
                ati_text = (
                    "ожидающий черновик отменён"
                )

            else:
                ati_text = (
                    "активная публикация "
                    "отсутствует"
                )

            if closed_now:
                response_text = (
                    f"**Заявка `{request_id}` "
                    "закрыта.**\n\n"
                    "Статус: больше не актуальна.\n"
                    f"Закрыл: "
                    f"{msg['author_name']}.\n"
                    f"ATI: {ati_text}.\n"
                    "Для Айюба: заявка "
                    "помечена неактивной."
                )

                reason = registry_entry.get(
                    "close_reason"
                )

                if reason:
                    response_text += (
                        "\nПричина: "
                        + str(reason)
                        + "."
                    )

            else:
                response_text = (
                    f"Заявка `{request_id}` "
                    "уже закрыта.\n\n"
                    "Повторное закрытие "
                    "не требуется."
                )

            close_status = (
                "closed"
                if closed_now
                else "already_closed"
            )

            authorized = True

        except PermissionError as exc:
            logger.warning(
                "MAX request close denied: "
                "user_id=%s error=%s",
                msg["user_id"],
                exc,
            )

            response_text = (
                "Закрытие отклонено.\n\n"
                "Закрыть заявку может только "
                "Навигатор, который её "
                "опубликовал, либо владелец."
            )

            close_result = None
            close_status = "forbidden"
            authorized = False

        except KeyError as exc:
            error_text = str(exc).strip("'")

            response_text = (
                "Не удалось закрыть заявку.\n\n"
                f"{error_text}."
            )

            close_result = None
            close_status = "not_found"
            authorized = None

        except ValueError as exc:
            response_text = (
                "Не удалось закрыть заявку.\n\n"
                f"{str(exc)}"
            )

            close_result = None
            close_status = "invalid_command"
            authorized = None

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
            "close_request": True,
            "status": close_status,
            "authorized": authorized,
            "result": close_result,
            "response_status": (
                send_result.get("status")
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

    if is_publication_request(text):
        publication = PublicationOrchestrator(
            settings
        )

        source = (
            f"max:{msg['chat_id']}:"
            f"{msg['message_id'] or 'no_message_id'}"
        )

        result = publication.prepare_from_text(
            text,
            source=source,
            source_chat_id=msg["chat_id"],
            source_message_id=(
                msg["message_id"] or None
            ),
            requested_by=(
                msg["user_id"] or None
            ),
        )

        approval = result.get("approval")
        client = MaxClient(settings)

        if approval is None:
            response_text = (
                build_missing_fields_message(
                    result.get(
                        "request",
                        {},
                    ).get(
                        "missing_fields",
                        [],
                    ),
                    author_name=msg[
                        "author_name"
                    ],
                )
            )

            if msg["chat_id"]:
                send_result = (
                    client.send_message(
                        response_text,
                        chat_id=msg[
                            "chat_id"
                        ],
                    )
                )
            elif msg["user_id"]:
                send_result = (
                    client.send_message(
                        response_text,
                        user_id=msg[
                            "user_id"
                        ],
                    )
                )
            else:
                send_result = {
                    "status": "skipped",
                    "reason": (
                        "missing_response_target"
                    ),
                }

            logger.info(
                "MAX publication request "
                "incomplete: chat_id=%s "
                "message_id=%s missing=%s",
                msg["chat_id"],
                msg["message_id"],
                result.get(
                    "request",
                    {},
                ).get(
                    "missing_fields",
                    [],
                ),
            )

            return {
                "ok": True,
                "publication_request": True,
                "valid": False,
                "missing_fields": result.get(
                    "request",
                    {},
                ).get(
                    "missing_fields",
                    [],
                ),
                "response_status": (
                    send_result.get("status")
                ),
            }

        if result.get("duplicate"):
            approval_id = str(
                approval["id"]
            )

            logger.info(
                "MAX duplicate publication skipped: "
                "chat_id=%s message_id=%s "
                "approval_id=%s status=%s",
                msg["chat_id"],
                msg["message_id"],
                approval_id,
                approval.get("status"),
            )

            return {
                "ok": True,
                "publication_request": True,
                "valid": True,
                "duplicate": True,
                "approval_id": approval_id,
                "approval_status": (
                    approval.get("status")
                ),
                "owner_delivery": (
                    "skipped_duplicate"
                ),
            }

        owner_id = str(
            settings.max_owner_user_id or ""
        ).strip()

        if not owner_id:
            logger.error(
                "MAX_OWNER_USER_ID is not "
                "configured for publication "
                "approval delivery"
            )

            return {
                "ok": True,
                "publication_request": True,
                "valid": True,
                "approval_created": True,
                "owner_delivery": (
                    "configuration_required"
                ),
            }

        approval_id = str(
            approval["id"]
        )

        preview = (
            result.get("ati_preview")
            or {}
        )

        registry_request = (
            result.get("registry_request")
            or {}
        )

        registry_request_id = str(
            registry_request.get(
                "request_id"
            )
            or ""
        ).strip()

        card_text = build_publication_card(
            result["request"],
            result["draft"],
            approval_id,
            ati_preview=preview,
        )

        if registry_request_id:
            card_text = (
                "**Заявка реестра:** "
                f"`{registry_request_id}`"
                "\n\n"
                + card_text
            )

        send_result = client.send_message(
            card_text,
            user_id=owner_id,
            buttons=publication_buttons(
                approval_id,
                ready_for_api=bool(
                    preview.get(
                        "ready_for_api"
                    )
                ),
                dry_run=settings.dry_run,
            ),
        )

        logger.info(
            "MAX publication approval prepared: "
            "chat_id=%s message_id=%s "
            "approval_id=%s owner_status=%s",
            msg["chat_id"],
            msg["message_id"],
            approval_id,
            send_result.get("status"),
        )

        return {
            "ok": True,
            "publication_request": True,
            "valid": True,
            "approval_id": approval_id,
            "registry_request_id": (
                registry_request_id
            ),
            "owner_delivery": (
                send_result.get("status")
            ),
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
