from __future__ import annotations

import hashlib
from typing import Any

import requests

from app.config import Settings
from app.data_models.request import AtiDraft, TransportRequest


class SheetsClient:
    """Google Sheets client via Apps Script Web App."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _enabled(self) -> bool:
        return bool(
            self.settings.google_sheets_enabled
            and self.settings.google_sheets_webapp_url
            and self.settings.google_sheets_secret
        )

    def _post(self, payload: dict[str, Any]) -> dict:
        if not self._enabled():
            return {
                "status": "disabled",
                "message": "Google Sheets disabled or missing GOOGLE_SHEETS_WEBAPP_URL / GOOGLE_SHEETS_SECRET",
            }

        body = dict(payload)
        body["secret"] = self.settings.google_sheets_secret

        try:
            response = requests.post(
                self.settings.google_sheets_webapp_url,
                json=body,
                timeout=30,
            )
        except requests.RequestException as exc:
            return {
                "status": "network_error",
                "message": str(exc),
            }

        text = response.text

        if response.status_code >= 400:
            return {
                "status": "http_error",
                "status_code": response.status_code,
                "text": text,
            }

        try:
            data = response.json()
        except Exception:
            return {
                "status": "invalid_json",
                "text": text,
            }

        return data

    def save_request_and_draft(self, request: TransportRequest, draft: AtiDraft) -> dict:
        request_data = request.model_dump()
        draft_data = draft.model_dump()

        if self.settings.google_sheets_dry_run:
            return {
                "status": "dry_run",
                "message": "Google Sheets write skipped because GOOGLE_SHEETS_DRY_RUN=true",
                "request": request_data,
                "draft": draft_data,
            }

        route_from = request.origin or ""
        route_to = request.destination or ""
        vehicle_or_cargo = request.vehicle or ""
        ready_date = request.ready_date or ""
        payment_type = request.payment_type or ""

        status = "Публикация" if request.is_valid_request else "Формирование"

        essence_parts = []
        if route_from or route_to:
            essence_parts.append(f"Маршрут: {route_from} — {route_to}".strip())
        if vehicle_or_cargo:
            essence_parts.append(f"Авто/груз: {vehicle_or_cargo}")
        if ready_date:
            essence_parts.append(f"Дата готовности: {ready_date}")
        if payment_type:
            essence_parts.append(f"Оплата: {payment_type}")
        if request.comment:
            essence_parts.append(f"Комментарий: {request.comment}")

        essence = "\n".join(essence_parts) or request.raw_text[:800]

        fingerprint_source = f"{request.source}\n{request.raw_text}".encode("utf-8")
        fingerprint = hashlib.sha256(fingerprint_source).hexdigest()[:24]
        tech_key = f"ati-agent:{fingerprint}"

        create_payload = {
            "action": "create_or_update_request",
            "channel": "ATI-Agent",
            "chat_id": request.source or "file",
            "contact_name": "ATI-Agent",
            "phone_or_account": "",
            "source": request.source or "file",
            "essence": essence[:800],
            "negotiation_result": "Заявка распознана ATI-Agent и подготовлена как черновик ATI.",
            "route_from": route_from,
            "route_to": route_to,
            "vehicle_or_cargo": vehicle_or_cargo,
            "ready_date": ready_date,
            "payment_type": payment_type,
            "preliminary_price": "",
            "status": status,
            "published_where": "ATI draft / dry-run" if self.settings.dry_run else "ATI",
            "performer_found": "Нет",
            "performer_data": "",
            "closed_by": "",
            "ayub_comment": (
                f"Черновик ATI: {draft.title}. "
                f"ATI_MODE={self.settings.ati_mode}; DRY_RUN={self.settings.dry_run}"
            )[:800],
            "tech_link": tech_key,
            "last_action": "ATI-Agent сформировал черновик ATI",
            "next_step": "Проверить и подтвердить публикацию ATI вручную",
            "priority": "Обычный",
            "responsible": "ATI-Agent",
        }

        create_result = self._post(create_payload)
        request_id = create_result.get("request_id", "")

        history_payload = {
            "action": "append_message_history",
            "request_id": request_id,
            "channel": "ATI-Agent",
            "chat_id": request.source or "file",
            "sender": "ATI-Agent input",
            "message_text": request.raw_text[:2000],
            "ayub_understanding": (
                f"origin={route_from}; destination={route_to}; vehicle={vehicle_or_cargo}; "
                f"ready_date={ready_date}; payment_type={payment_type}; valid={request.is_valid_request}"
            )[:800],
            "ayub_action": "Подготовил черновик ATI и записал в реестр.",
            "tech_link": tech_key,
        }

        history_result = self._post(history_payload)

        return {
            "status": "ok" if create_result.get("ok") else "error",
            "create_result": create_result,
            "history_result": history_result,
            "request": request_data,
            "draft": draft_data,
        }
