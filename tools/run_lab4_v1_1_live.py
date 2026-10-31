"""Three explicit, bounded Qwen calls on preserved real-source materials."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from researchradar.evidence_analysis import analyze_research, context_for
from researchradar.llm import BudgetedOpenRouter, MODEL


ROOT = Path(__file__).resolve().parents[1]


def cases() -> list[tuple[str, dict, str]]:
    old = json.loads((ROOT / "experiments/lab4/live_qwen_evidence.json").read_text(
        encoding="utf-8"))["context"]
    ocean = json.loads((ROOT / "run_output/lab4_v1_1_ocean_search.json").read_text(
        encoding="utf-8"))["search"]
    old_paper = copy.deepcopy(next(x for x in old["materials"] if x["kind"] == "scientific"))
    related = copy.deepcopy(ocean)
    unrelated = {"question": "Compare unrelated research and news topics",
                 "materials": {"scientific": [old_paper],
                               "news": [copy.deepcopy(ocean["materials"]["news"][0])]}}
    sparse_paper = copy.deepcopy(old_paper)
    sparse_paper["abstract"], sparse_paper["text_scope"] = None, "metadata"
    sparse = {"question": "Assess evidence when only metadata and a headline are available",
              "materials": {"scientific": [sparse_paper],
                            "news": [copy.deepcopy(ocean["materials"]["news"][0])]}}
    return [("related_real_pair", related, "current live OpenAlex and Google News RSS search"),
            ("unrelated_real_pair", unrelated,
             "controlled pairing of preserved real OpenAlex paper and current real news"),
            ("metadata_only_real_pair", sparse,
             "controlled withholding of a real abstract; real metadata and headline")]


def run(output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("choose a new empty output directory for paid calls")
    output.mkdir(parents=True, exist_ok=True)
    client = BudgetedOpenRouter(per_call_usd=0.05, max_retries=0)
    rows = []
    for name, research, origin in cases():
        before = client.summary()
        response_path = output / f"{name}_response.json"
        result = analyze_research(research, mode="live", client=client,
            save_response_path=response_path, input_rate_per_million=0.32,
            output_rate_per_million=1.8, request_id=str(uuid4()))
        after = client.summary()
        row = {"case": name, "at_utc": datetime.now(timezone.utc).isoformat(),
               "material_origin": origin, "model": MODEL,
               "context": context_for(research), "result": result,
               "response": json.loads(response_path.read_text(encoding="utf-8"))
                           if response_path.exists() else None,
               "expense_delta": {"calls": after.total_calls - before.total_calls,
                   "actual_usd": round(after.actual_usd - before.actual_usd, 9),
                   "uncertain_estimate_usd": round(after.uncertain_estimate_usd -
                                                    before.uncertain_estimate_usd, 9)}}
        (output / f"{name}.json").write_text(json.dumps(row, ensure_ascii=False,
                indent=2) + "\n", encoding="utf-8")
        rows.append({"case": name, "status": result["status"],
                     "reason": result.get("reason"), **row["expense_delta"]})
        print(name, result["status"], result.get("reason", ""), row["expense_delta"])
    summary = {"model": MODEL, "material_kind": "real_source_with_controlled_pairing",
               "calls_attempted": len(rows), "calls_recorded": sum(x["calls"] for x in rows),
               "usable_preliminary": sum(x["status"] == "usable_preliminary" for x in rows),
               "rejected": sum(x["status"] == "rejected" for x in rows),
               "unavailable": sum(x["status"] == "unavailable" for x in rows),
               "actual_usd": round(sum(x["actual_usd"] for x in rows), 9),
               "uncertain_estimate_usd": round(sum(x["uncertain_estimate_usd"] for x in rows), 9),
               "cases": rows}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False,
            indent=2) + "\n", encoding="utf-8")
    print(summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="authorize three paid calls")
    parser.add_argument("--output", type=Path, default=Path("run_output/lab4_v1_1_live"))
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required for paid calls")
    run(args.output)
