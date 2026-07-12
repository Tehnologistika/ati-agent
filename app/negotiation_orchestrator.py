from app.config import Settings
from app.data_models.negotiation import (
    Carrier,
    MessageDeliveryStatus,
    MessageDirection,
    NegotiationAction,
    NegotiationMessage,
    NegotiationSession,
    NegotiationStatus,
    RouteContext,
)
from app.integrations.anthropic_client import AnthropicClient
from app.integrations.ati_messenger_client import AtiMessengerClient
from app.services.audit_writer import write_event
from app.services.negotiation_message_builder import NegotiationMessageBuilder
from app.services.negotiation_policy import NegotiationPolicy
from app.services.negotiation_repository import NegotiationRepository


class NegotiationOrchestrator:
    """Coordinates negotiation drafts, inbound analysis, approval and ATI delivery."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = NegotiationRepository(settings.database_url)
        self.policy = NegotiationPolicy()
        self.builder = NegotiationMessageBuilder(AnthropicClient(settings))
        self.messenger = AtiMessengerClient(settings)

    def create_session(
        self,
        *,
        ati_carrier_id: str,
        carrier_name: str | None,
        ati_conversation_id: str | None,
        route: RouteContext,
        target_rate: int | None = None,
        max_rate: int | None = None,
    ) -> NegotiationSession:
        if target_rate is not None and max_rate is not None and target_rate > max_rate:
            raise ValueError("target_rate cannot be greater than max_rate")
        session = NegotiationSession(
            carrier=Carrier(
                ati_carrier_id=ati_carrier_id,
                name=carrier_name,
                ati_conversation_id=ati_conversation_id,
            ),
            route=route,
            target_rate=target_rate,
            max_rate=max_rate,
        )
        self.repository.save_session(session)
        write_event("negotiation_created", session.model_dump(), path=self.settings.events_log_path)
        return session

    def prepare_initial_message(self, negotiation_id: str) -> dict:
        session = self.repository.get_session(negotiation_id)
        decision = self.policy.initial_decision()
        text = self.builder.build(session, decision)
        message = NegotiationMessage(
            direction=MessageDirection.OUTBOUND,
            purpose=decision.purpose,
            text=text,
            delivery_status=MessageDeliveryStatus.AWAITING_APPROVAL,
        )
        session.messages.append(message)
        session.status = NegotiationStatus.AWAITING_APPROVAL
        approval = self.repository.create_approval(session.id, message.id)
        self.repository.save_session(session)
        result = {"session": session.model_dump(), "decision": decision.model_dump(), "approval": approval.model_dump()}
        write_event("negotiation_message_prepared", result, path=self.settings.events_log_path)
        return result

    def process_inbound_message(
        self,
        negotiation_id: str,
        text: str,
        external_message_id: str | None = None,
    ) -> dict:
        session = self.repository.get_session(negotiation_id)
        inbound = NegotiationMessage(
            direction=MessageDirection.INBOUND,
            text=text,
            delivery_status=MessageDeliveryStatus.RECEIVED,
            external_message_id=external_message_id,
        )
        session.messages.append(inbound)

        decision = self.policy.decide(session, text)
        if decision.offer is not None:
            session.offers.append(decision.offer)
            session.status = NegotiationStatus.RATE_RECEIVED

        outbound_text = self.builder.build(session, decision, inbound_text=text)
        outbound = NegotiationMessage(
            direction=MessageDirection.OUTBOUND,
            purpose=decision.purpose,
            text=outbound_text,
            delivery_status=MessageDeliveryStatus.AWAITING_APPROVAL,
        )
        session.messages.append(outbound)
        session.status = (
            NegotiationStatus.DECLINED
            if decision.action == NegotiationAction.CLOSE_UNAVAILABLE
            else NegotiationStatus.AWAITING_APPROVAL
        )
        approval = self.repository.create_approval(session.id, outbound.id)
        self.repository.save_session(session)
        result = {
            "session": session.model_dump(),
            "decision": decision.model_dump(),
            "approval": approval.model_dump(),
        }
        write_event("carrier_reply_processed", result, path=self.settings.events_log_path)
        return result

    def _authorize_owner(self, approved_by: str) -> None:
        """Allow MAX approvals only from the configured owner account."""

        if not self.settings.max_enabled:
            return
        if not self.settings.max_owner_user_id:
            raise RuntimeError("MAX_OWNER_USER_ID must be configured before approvals are enabled")
        if str(approved_by) != str(self.settings.max_owner_user_id):
            raise PermissionError("Only the configured MAX owner may approve ATI messages")

    @staticmethod
    def _partner_contact_id(ati_carrier_id: str) -> str:
        """ATI Messenger expects partner alias in the form ATI_CODE.CONTACT_ID."""

        value = ati_carrier_id.strip()
        return value if "." in value else f"{value}.0"

    def approve_and_send(self, approval_id: str, approved_by: str) -> dict:
        self._authorize_owner(approved_by)

        approval = self.repository.approve(approval_id, approved_by)
        session = self.repository.get_session(approval.negotiation_id)
        message = next((item for item in session.messages if item.id == approval.message_id), None)
        if message is None:
            raise KeyError(f"Message not found for approval: {approval.message_id}")

        self.repository.consume(approval.id, message.id)
        message.delivery_status = MessageDeliveryStatus.APPROVED
        message.approved_by = approved_by

        conversation_id = session.carrier.ati_conversation_id
        dialog_creation = None
        if not conversation_id:
            partner_id = self._partner_contact_id(session.carrier.ati_carrier_id)
            dialog_creation = self.messenger.create_dialog(
                partner_id,
                partner_name=session.carrier.name,
                description=f"ТехноЛогистика: {session.route.origin} — {session.route.destination}",
                approval_consumed=True,
            )
            dialog_status = dialog_creation.get("status")
            if dialog_status == "created":
                response = dialog_creation.get("response") or {}
                conversation_id = response.get("id")
                session.carrier.ati_conversation_id = conversation_id
            elif dialog_status == "dry_run":
                conversation_id = f"dry-run:{partner_id}"
            else:
                conversation_id = None

        if not conversation_id:
            delivery = {
                "status": (dialog_creation or {}).get("status", "blocked"),
                "message": (dialog_creation or {}).get("message", "ATI dialog could not be created"),
            }
        else:
            delivery = self.messenger.send_message(
                conversation_id,
                message.text,
                approval_consumed=True,
            )

        status = delivery.get("status")
        if status == "sent":
            message.delivery_status = MessageDeliveryStatus.SENT
            session.status = NegotiationStatus.AWAITING_REPLY
        elif status == "dry_run":
            message.delivery_status = MessageDeliveryStatus.DRY_RUN
            session.status = NegotiationStatus.AWAITING_REPLY
        elif status == "blocked":
            message.delivery_status = MessageDeliveryStatus.BLOCKED
            session.status = NegotiationStatus.ERROR
        else:
            message.delivery_status = MessageDeliveryStatus.FAILED
            session.status = NegotiationStatus.ERROR

        self.repository.save_session(session)
        result = {
            "session": session.model_dump(),
            "dialog_creation": dialog_creation,
            "delivery": delivery,
        }
        write_event("approved_message_delivery_attempted", result, path=self.settings.events_log_path)
        return result
