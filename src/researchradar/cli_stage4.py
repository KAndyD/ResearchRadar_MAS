"""Ordinary research with bounded, evidence-checked optional Qwen analysis."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from .coordination import research_stage2
from .evidence_analysis import analyze_research
from .frozen import load_frozen
from .llm import BudgetedOpenRouter
from .negotiation import review_research
from .scientific import Arxiv, Crossref
from .sources import GoogleNewsRSS, OpenAlex


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="ResearchRadar evidence-aware research")
    parser.add_argument("question")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--allocation", choices=("centralized", "contract-net"),
                        default="centralized")
    parser.add_argument("--resource-policy", choices=("baseline", "negotiation"),
                        default="negotiation")
    parser.add_argument("--credits", type=int, default=3)
    parser.add_argument("--slots", type=int)
    parser.add_argument("--analysis", choices=("off", "recorded", "live"), default="off")
    parser.add_argument("--recorded-analysis", type=Path)
    parser.add_argument("--save-recorded", type=Path)
    parser.add_argument("--input-rate", type=float)
    parser.add_argument("--output-rate", type=float)
    parser.add_argument("--output", type=Path, default=Path("run_output/stage4-result.json"))
    args = parser.parse_args()
    if args.credits < 0 or args.credits > 50 or args.slots is not None and args.slots < 1:
        parser.error("invalid verification resource capacity")
    if args.analysis == "recorded" and args.recorded_analysis is None:
        parser.error("--recorded-analysis required for recorded mode")
    if args.analysis == "live" and (args.mode != "live" or args.input_rate is None
                                    or args.output_rate is None):
        parser.error("live analysis requires --mode live and verified token rates")
    if args.save_recorded and args.analysis != "live":
        parser.error("--save-recorded requires live analysis")
    sources = load_frozen() if args.mode == "demo" else {
        "openalex": OpenAlex(), "crossref": Crossref(), "arxiv": Arxiv(),
        "news": GoogleNewsRSS()}

    async def search_and_review():
        search = await research_stage2(args.question, sources,
            mechanism=args.allocation, task_timeout=30 if args.mode == "live" else 0.5,
            deadline_seconds=75 if args.mode == "live" else 5)
        review = await review_research(search, mode=args.resource_policy,
            credits=args.credits, concurrent_slots=args.slots,
            timeout=30 if args.mode == "live" else 0.05)
        return search, review

    search, review = asyncio.run(search_and_review())
    client = BudgetedOpenRouter() if args.analysis == "live" else None
    before = client.summary() if client else None
    analysis = analyze_research(search, mode=args.analysis, client=client,
        recorded_path=args.recorded_analysis, save_response_path=args.save_recorded,
        input_rate_per_million=args.input_rate,
        output_rate_per_million=args.output_rate, request_id=str(uuid4()))
    if client:
        after = client.summary()
        analysis["expense_delta"] = {
            "actual_usd": round(after.actual_usd - before.actual_usd, 9),
            "uncertain_estimate_usd": round(
                after.uncertain_estimate_usd - before.uncertain_estimate_usd, 9),
            "calls": after.total_calls - before.total_calls}
    result = {"mode": args.mode, "search": search, "review": review,
              "evidence_analysis": analysis}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"search {search['metrics']['completed_tasks']}/{search['metrics']['task_count']}; "
          f"checks {review['metrics']['completed_checks']}; "
          f"analysis {analysis['status']}")
    if analysis["status"] == "usable_preliminary":
        detail = analysis["analysis"]
        print(f"Topic (model interpretation): {detail['research_topic']['text']}")
        for kind in ("scientific", "news"):
            item = detail[f"{kind}_evidence"]
            if item:
                print(f"{kind} exact {item['text_scope']} excerpt [{item['source_id']}]: "
                      f"{item['text']}")
        print(f"Relation (unverified): {detail['relation']['category']}; "
              f"claim support: {detail['claim_support']}; "
              f"next check: {detail['next_check']}")
        print(f"Model explanation (unverified): {detail['explanation']['text']}")
    print(f"Result and traces: {args.output}")


if __name__ == "__main__":
    main()
