"""Evidence-aware research with baseline or mediated verification budgeting."""
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
from .negotiation import review_research
from .planning import qwen_alternative, validate_alternative
from .scientific import Arxiv, Crossref
from .sources import GoogleNewsRSS, OpenAlex


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="ResearchRadar verification budget study")
    parser.add_argument("question")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--allocation", choices=("centralized", "contract-net"),
                        default="centralized")
    parser.add_argument("--resource-policy", choices=("baseline", "negotiation"),
                        default="negotiation")
    parser.add_argument("--credits", type=int, default=3)
    parser.add_argument("--slots", type=int, help="maximum simultaneous checks")
    parser.add_argument("--llm", choices=("off", "recorded", "live"), default="off")
    parser.add_argument("--recorded-plan", type=Path)
    parser.add_argument("--input-rate", type=float)
    parser.add_argument("--output-rate", type=float)
    parser.add_argument("--output", type=Path, default=Path("run_output/stage3-result.json"))
    args = parser.parse_args()
    if args.credits < 0 or args.credits > 50:
        parser.error("--credits must be 0..50")
    if args.slots is not None and args.slots < 1:
        parser.error("--slots must be at least 1")
    alternative = "distributed task allocation" if args.mode == "demo" else None
    if args.llm == "recorded":
        if not args.recorded_plan:
            parser.error("--recorded-plan required with --llm recorded")
        plan = json.loads(args.recorded_plan.read_text(encoding="utf-8"))
        if plan.get("question") != args.question:
            parser.error("recorded plan belongs to another question")
        alternative = validate_alternative(args.question,
            json.dumps({"alternative_query": plan["alternative_query"]}))
    elif args.llm == "live":
        if args.mode != "live" or args.input_rate is None or args.output_rate is None:
            parser.error("live Qwen requires --mode live and verified token rates")
        alternative = qwen_alternative(args.question, BudgetedOpenRouter(),
                    input_rate_per_million=args.input_rate,
                    output_rate_per_million=args.output_rate,
                    request_id=str(uuid4()))
    sources = load_frozen() if args.mode == "demo" else {
        "openalex": OpenAlex(), "crossref": Crossref(), "arxiv": Arxiv(),
        "news": GoogleNewsRSS()}

    async def run():
        search = await research_stage2(args.question, sources,
                    mechanism=args.allocation, alternative=alternative,
                    task_timeout=30 if args.mode == "live" else 0.5,
                    deadline_seconds=75 if args.mode == "live" else 5)
        review = await review_research(search, mode=args.resource_policy,
                                       credits=args.credits,
                                       concurrent_slots=args.slots,
                                       timeout=30 if args.mode == "live" else 0.05)
        return {"mode": args.mode, "llm_mode": args.llm,
                "alternative_query": alternative, "search": search, "review": review}

    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = result["review"]["metrics"]
    print(f"{args.resource_policy}: {checks['completed_checks']} checks, "
          f"{checks['granted_units']}/{args.credits} credits, "
          f"utility {checks['estimated_utility']:.2f}, "
          f"Jain {checks['jain_normalized_satisfaction']:.3f}, "
          f"{checks['messages']} review messages")
    print(f"Evidence and protocol trace: {args.output}")
    if result["search"]["errors"]:
        print("Search errors:", result["search"]["errors"])


if __name__ == "__main__":
    main()
