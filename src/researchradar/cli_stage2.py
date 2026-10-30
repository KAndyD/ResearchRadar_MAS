"""Stage 2 multi-source CLI with explicit coordination and LLM choices."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from .coordination import research_stage2
from .frozen import load_frozen
from .llm import BudgetedOpenRouter
from .planning import qwen_alternative, validate_alternative
from .scientific import Arxiv, Crossref
from .sources import GDELT, GoogleNewsRSS, OpenAlex


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="ResearchRadar MAS task allocation research")
    parser.add_argument("question", help="scientific research topic")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--coordination", choices=("centralized", "contract-net"),
                        default="centralized")
    parser.add_argument("--news-source", choices=("rss", "gdelt"), default="rss")
    parser.add_argument("--llm", choices=("off", "recorded", "live"), default="off")
    parser.add_argument("--recorded-plan", type=Path)
    parser.add_argument("--input-rate", type=float,
                        help="verified USD per million input tokens, required for live LLM")
    parser.add_argument("--output-rate", type=float,
                        help="verified USD per million output tokens, required for live LLM")
    parser.add_argument("--output", type=Path, default=Path("run_output/stage2-result.json"))
    args = parser.parse_args()
    alternative = None
    if args.llm == "recorded":
        if not args.recorded_plan:
            parser.error("--recorded-plan is required with --llm recorded")
        plan = json.loads(args.recorded_plan.read_text(encoding="utf-8"))
        if plan.get("question") != args.question:
            parser.error("recorded plan belongs to a different question")
        alternative = validate_alternative(args.question,
                         json.dumps({"alternative_query": plan["alternative_query"]}))
    elif args.llm == "live":
        if args.mode != "live":
            parser.error("live LLM requires --mode live")
        if args.input_rate is None or args.output_rate is None:
            parser.error("verified --input-rate and --output-rate are required")
        alternative = qwen_alternative(args.question, BudgetedOpenRouter(),
                    input_rate_per_million=args.input_rate,
                    output_rate_per_million=args.output_rate,
                    request_id=str(uuid4()))
    elif args.mode == "demo":
        alternative = "distributed task allocation"
    sources = (load_frozen() if args.mode == "demo" else {
        "openalex": OpenAlex(), "crossref": Crossref(), "arxiv": Arxiv(),
        "news": GoogleNewsRSS() if args.news_source == "rss" else GDELT()})
    result = asyncio.run(research_stage2(args.question, sources,
                         mechanism=args.coordination, alternative=alternative,
                         task_timeout=30 if args.mode == "live" else 0.5,
                         deadline_seconds=75 if args.mode == "live" else 5))
    result["mode"] = args.mode
    result["llm_mode"] = args.llm
    result["alternative_query"] = alternative
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.coordination}: {result['metrics']['completed_tasks']}/{result['metrics']['task_count']} "
          f"tasks; {result['metrics']['messages']} messages; "
          f"{len(result['materials']['scientific'])} scientific, "
          f"{len(result['materials']['news'])} news")
    print(f"Result and trace: {args.output}")
    if result["errors"]:
        print("Source errors:", result["errors"])


if __name__ == "__main__":
    main()
