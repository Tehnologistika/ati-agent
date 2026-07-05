from app.config import Settings


class MaxClient:
    """MAX Messenger client placeholder."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def send_approval_request(self, text: str) -> dict:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "MAX approval request skipped because DRY_RUN=true",
                "text": text,
            }
        raise NotImplementedError("Real MAX messaging will be implemented after webhook setup.")
