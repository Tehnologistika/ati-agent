from app.config import Settings


class GmailClient:
    """Gmail client placeholder for notifications and future drafts."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def create_notification(self, subject: str, body: str) -> dict:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "Gmail notification skipped because DRY_RUN=true",
                "subject": subject,
                "body": body,
            }
        raise NotImplementedError("Real Gmail integration will be implemented after credentials setup.")
