import json
from pathlib import Path

from app.config import get_settings
from app.orchestrator import Orchestrator


raw_text = Path("examples/sample_max_request.txt").read_text(encoding="utf-8")
settings = get_settings()
orchestrator = Orchestrator(settings)
result = orchestrator.process_text_request(raw_text, source="file")
print(json.dumps(result, ensure_ascii=False, indent=2))
