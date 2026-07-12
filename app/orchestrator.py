from app.config import Settings
from app.integrations.ati_client import AtiClient
from app.integrations.gmail_client import GmailClient
from app.integrations.max_client import MaxClient
from app.integrations.sheets_client import SheetsClient
from app.services.audit_writer import write_event
from app.services.draft_builder import build_ati_draft
from app.services.request_parser import parse_transport_request


class Orchestrator:
    """Coordinates safe MVP flow: parse request -> build draft -> record result."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.ati = AtiClient(settings)
        self.max = MaxClient(settings)
        self.gmail = GmailClient(settings)
        self.sheets = SheetsClient(settings)

    def process_text_request(self, raw_text: str, source: str = "manual") -> dict:
        request = parse_transport_request(raw_text, source=source)
        draft = build_ati_draft(request, dry_run=self.settings.dry_run)

        sheets_result = self.sheets.save_request_and_draft(request, draft)
        publication_result = self.ati.publish_load(draft)

        result = {
            "request": request.model_dump(),
            "ati_draft": draft.model_dump(),
            "sheets_result": sheets_result,
            "publication_result": publication_result,
        }

        write_event("request_processed", result, path=self.settings.events_log_path)
        return result
