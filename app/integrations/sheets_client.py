from app.config import Settings
from app.data_models.request import AtiDraft, TransportRequest


class SheetsClient:
    """Google Sheets client placeholder.

    MVP can start by printing/saving rows locally. Real Google Sheets write is added
    after service account credentials are configured.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def save_request_and_draft(self, request: TransportRequest, draft: AtiDraft) -> dict:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "Google Sheets write skipped because DRY_RUN=true",
                "request": request.model_dump(),
                "draft": draft.model_dump(),
            }
        raise NotImplementedError("Real Google Sheets integration will be implemented after credentials setup.")
