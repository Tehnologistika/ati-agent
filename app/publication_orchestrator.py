from __future__ import annotations

from app.config import Settings
from app.data_models.ati_publication import (
    AtiPublicationBuildResult,
)
from app.data_models.publication import (
    PublicationApproval,
)
from app.integrations.ati_client import AtiClient
from app.services.audit_writer import write_event
from app.services.draft_builder import build_ati_draft
from app.services.publication_preview import (
    build_publication_preview,
)
from app.services.publication_repository import (
    PublicationApprovalRepository,
)
from app.services.publication_snapshot import (
    freeze_snapshot,
    verify_snapshot,
)
from app.services.request_parser import (
    parse_transport_request,
)
from app.services.request_registry import (
    RequestRegistryRepository,
)


class PublicationOrchestrator:
    """Prepare and approve ATI load publications."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = (
            PublicationApprovalRepository(
                settings.database_url
            )
        )

        self.registry = (
            RequestRegistryRepository(
                settings.database_url
            )
        )

        self.ati = AtiClient(settings)

    def _authorize_owner(
        self,
        actor_id: str,
    ) -> None:
        if not self.settings.max_enabled:
            return

        owner_id = str(
            self.settings.max_owner_user_id or ""
        ).strip()

        if not owner_id:
            raise RuntimeError(
                "MAX_OWNER_USER_ID must be configured"
            )

        if str(actor_id) != owner_id:
            raise PermissionError(
                "Only the configured MAX owner may "
                "approve ATI publications"
            )

    def prepare_from_text(
        self,
        raw_text: str,
        *,
        source: str,
        source_chat_id: str,
        source_message_id: str | None,
        requested_by: str | None,
    ) -> dict:
        request = parse_transport_request(
            raw_text,
            source=source,
        )

        draft = build_ati_draft(
            request,
            dry_run=self.settings.dry_run,
        )

        if not request.is_valid_request:
            result = {
                "request": request.model_dump(),
                "draft": draft.model_dump(),
                "ati_preview": None,
                "approval": None,
            }

            write_event(
                "publication_request_incomplete",
                result,
                path=self.settings.events_log_path,
            )

            return result

        source_channel = (
            str(source or "")
            .split(":", 1)[0]
            .strip()
            or "unknown"
        )

        registry_request, registry_created = (
            self.registry.create_or_get(
                request=request,
                source_channel=source_channel,
                source_chat_id=str(
                    source_chat_id
                ),
                source_message_id=(
                    str(source_message_id)
                    if source_message_id
                    else None
                ),
                author_user_id=(
                    str(requested_by)
                    if requested_by
                    else None
                ),
            )
        )

        approval = PublicationApproval(
            request=request,
            draft=draft,
            registry_request_id=(
                registry_request.request_id
            ),
            source_chat_id=str(
                source_chat_id
            ),
            source_message_id=(
                str(source_message_id)
                if source_message_id
                else None
            ),
            requested_by=(
                str(requested_by)
                if requested_by
                else None
            ),
        )

        preview = build_publication_preview(
            request,
            approval.id,
            self.settings,
        )

        frozen_preview, preview_hash = (
            freeze_snapshot(
                preview.model_dump(
                    mode="json"
                )
            )
        )

        approval.ati_preview = frozen_preview
        approval.ati_preview_hash = preview_hash

        stored, created = (
            self.repository.create_or_get(
                approval
            )
        )

        # При повторном webhook возвращается
        # именно ранее сохранённый снимок.
        stored_preview = stored.ati_preview

        result = {
            "request": stored.request.model_dump(),
            "draft": stored.draft.model_dump(),
            "ati_preview": stored_preview,
            "approval": stored.model_dump(),
            "duplicate": not created,
            "registry_request": (
                registry_request.model_dump(
                    mode="json"
                )
            ),
            "registry_duplicate": (
                not registry_created
            ),
        }

        event_name = (
            "publication_approval_created"
            if created
            else "publication_duplicate_skipped"
        )

        write_event(
            event_name,
            result,
            path=self.settings.events_log_path,
        )

        return result

    def reject(
        self,
        approval_id: str,
        rejected_by: str,
    ) -> dict:
        self._authorize_owner(rejected_by)

        approval = self.repository.reject(
            approval_id,
            rejected_by,
        )

        result = {
            "approval": approval.model_dump(),
            "status": "rejected",
        }

        write_event(
            "publication_rejected",
            result,
            path=self.settings.events_log_path,
        )

        return result

    def approve_and_publish(
        self,
        approval_id: str,
        approved_by: str,
    ) -> dict:
        self._authorize_owner(approved_by)

        pending = self.repository.get(
            approval_id
        )

        if not pending.registry_request_id:
            raise RuntimeError(
                "Публикация заблокирована: "
                "approval не связан с единым "
                "реестром заявок"
            )

        registry_request = self.registry.get(
            pending.registry_request_id
        )

        if not registry_request.is_active:
            raise RuntimeError(
                "Публикация заблокирована: "
                f"заявка "
                f"{registry_request.request_id} "
                "уже закрыта и не актуальна"
            )

        # Ничего не перестраиваем при нажатии
        # кнопки: используем только тот снимок,
        # который видел владелец.
        snapshot = verify_snapshot(
            pending.ati_preview,
            pending.ati_preview_hash,
        )

        preview = (
            AtiPublicationBuildResult
            .model_validate(snapshot)
        )

        # В DRY_RUN разрешаем проверять полный
        # цикл кнопки подтверждения.
        # В реальном режиме незавершённая заявка
        # никогда не должна попасть в ATI.
        if (
            not self.settings.dry_run
            and not preview.ready_for_api
        ):
            missing = ", ".join(
                preview.missing_fields
            )

            raise RuntimeError(
                "Публикация заблокирована: "
                "не заполнены обязательные поля ATI: "
                f"{missing}"
            )

        approval = self.repository.approve(
            approval_id,
            approved_by,
        )

        publication_result = self.ati.publish_load(
            approval.draft
        )

        publication_result[
            "ati_preview"
        ] = snapshot

        publication_result[
            "ati_preview_hash"
        ] = pending.ati_preview_hash

        publication_result[
            "registry_request_id"
        ] = registry_request.request_id

        approval = self.repository.consume(
            approval_id,
            publication_result,
        )

        result = {
            "approval": approval.model_dump(),
            "ati_preview": snapshot,
            "ati_preview_hash": (
                pending.ati_preview_hash
            ),
            "publication_result": (
                publication_result
            ),
        }

        write_event(
            "publication_attempted",
            result,
            path=self.settings.events_log_path,
        )

        return result
