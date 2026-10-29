from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .engine import research
from .sources import FixtureSource, GDELT, OpenAlex


def main() -> None:
    parser = argparse.ArgumentParser(description="ResearchRadar MAS laboratory 1")
    parser.add_argument("question", help="Research topic; English works best with live APIs")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--output", type=Path, default=Path("run_output/result.json"))
    args = parser.parse_args()
    science, news = ((FixtureSource("scientific"), FixtureSource("news"))
                     if args.mode == "demo" else (OpenAlex(), GDELT()))
    result = asyncio.run(research(args.question, science, news))
    result["mode"] = args.mode
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["summary"])
    print(f"Result and trace: {args.output}")
    if result["errors"]:
        print("Source errors:", result["errors"])


if __name__ == "__main__":
    main()
