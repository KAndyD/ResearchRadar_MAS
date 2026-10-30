"""Independently validate saved negotiation measurements and aggregates."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def verify(folder: Path) -> dict:
    with (folder / "raw.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    paired = json.loads((folder / "paired.json").read_text(encoding="utf-8"))
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    inputs = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))
    if (len(rows) != metadata["runs"] or
            len(rows) != len(metadata["scenarios"]) * metadata["repeats"] * 2 or
            len(inputs) != len(metadata["scenarios"]) * metadata["repeats"] or
            len({(x["scenario"], x["seed"], x["mode"]) for x in rows}) != len(rows)):
        raise AssertionError("missing or duplicate experimental rows")
    if metadata["frozen_sha256"] != sha256((ROOT / "data/frozen_sources.json").read_bytes()).hexdigest():
        raise AssertionError("frozen input hash differs")
    if metadata["scenarios_sha256"] != sha256((ROOT / "experiments/lab3/scenarios.json").read_bytes()).hexdigest():
        raise AssertionError("scenario configuration hash differs")
    for row in rows:
        plan = json.loads(row["plan"])
        if (int(row["spent_units"]) > int(row["credits"]) or
                int(row["held_units"]) != 0 or
                sum(plan.values()) > int(row["credits"]) or
                int(row["budget_violations"]) or int(row["slot_violations"])):
            raise AssertionError(f"resource violation: {row['scenario']}/{row['seed']}")
    for item in summary:
        group = [x for x in rows if x["scenario"] == item["scenario"]
                 and x["mode"] == item["mode"]]
        if len(group) != item["runs"]:
            raise AssertionError("summary group size")
        for metric in ("estimated_utility", "jain_normalized_satisfaction", "messages",
                       "wall_ms", "completed_checks"):
            value = statistics.mean(float(x[metric]) for x in group)
            if abs(value - item[metric + "_mean"]) > 0.000011:
                raise AssertionError(f"summary mismatch: {item['scenario']}/{metric}")
    for item in paired:
        differences = []
        for seed in range(metadata["repeats"]):
            group = {x["mode"]: x for x in rows if x["scenario"] == item["scenario"]
                     and int(x["seed"]) == seed}
            if set(group) != {"baseline", "negotiation"}:
                raise AssertionError("unpaired seed")
            differences.append(float(group["negotiation"]["estimated_utility"])
                               - float(group["baseline"]["estimated_utility"]))
        if abs(statistics.mean(differences)
               - item["estimated_utility_difference_mean"]) > 0.000011:
            raise AssertionError("paired utility mismatch")
    if len(list((folder / "traces").glob("*.json"))) != len(metadata["scenarios"]) * 2:
        raise AssertionError("missing protocol traces")
    if len(list(folder.glob("*.svg"))) != 4:
        raise AssertionError("missing vector charts")
    return {"rows": len(rows), "pairs": len(rows) // 2,
            "scenarios": len(metadata["scenarios"]), "resource_violations": 0,
            "frozen_sha256": metadata["frozen_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path,
                        default=ROOT / "experiments/lab3/results")
    args = parser.parse_args()
    print(json.dumps(verify(args.results), indent=2))
