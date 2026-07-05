from app.config import Settings
from app.data_models.request import AtiDraft


class AtiClient:
    """ATI.su API client placeholder.

    MVP rule: no real publication while settings.dry_run is True.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def publish_load(self, draft: AtiDraft) -> dict:
        if self.settings.dry_run:
            return {
                "status": "dry_run",
                "message": "ATI publication skipped because DRY_RUN=true",
                "draft": draft.model_dump(),
            }
        raise NotImplementedError("Real ATI publication will be implemented after API access is confirmed.")
