import json
import argparse
from pathlib import Path

from app.config import get_settings
from app.orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="ATI-Agent MVP CLI")
    parser.add_argument(
        "--input", 
        type=str, 
        default="examples/sample_max_request.txt",
        help="Path to the input text file (default: examples/sample_max_request.txt)"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {args.input} not found.")
        return

    raw_text = input_path.read_text(encoding="utf-8")
    settings = get_settings()
    orchestrator = Orchestrator(settings)
    result = orchestrator.process_text_request(raw_text, source="file")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
