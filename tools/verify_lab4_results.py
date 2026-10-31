"""Independently recompute Lab 4 metrics from preserved probe traces."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import statistics

from run_lab4_experiments import (BASELINE, EXPECTED_BASELINE_SHA, SCENARIOS,
                                  correct, violation)


def verify(folder: Path) -> dict:
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    assert sha256(BASELINE.read_bytes()).hexdigest() == EXPECTED_BASELINE_SHA
    assert metadata["baseline_sha256"] == EXPECTED_BASELINE_SHA
    assert metadata["scenarios_sha256"] == sha256(SCENARIOS.read_bytes()).hexdigest()
    assert metadata["network_and_paid_llm_calls"] == 0
    with (folder / "raw.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    repeats = metadata["repeats"]
    assert metadata["runs"] == len(rows) == 2 * repeats * len(scenarios)
    assert len({(r["scenario"], int(r["seed"]), r["variant"]) for r in rows}) == len(rows)
    known = {s["id"]: s for s in scenarios}
    assert len(known) == len(scenarios)
    traces = {}
    for row in rows:
        scenario, seed, variant = row["scenario"], int(row["seed"]), row["variant"]
        assert scenario in known and row["class"] == known[scenario]["class"]
        assert 0 <= seed < repeats and variant in {"baseline", "protected"}
        trace_path = (folder / row["trace"]).resolve()
        assert trace_path.is_relative_to(folder.resolve()) and trace_path.is_file()
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["scenario"] == scenario and trace["seed"] == seed
        assert trace["variant"] == variant
        expected_origin = "historical_snapshot" if variant == "baseline" else "current_src"
        assert trace["module_origin"] == expected_origin
        assert int(row["policy_violation"]) == int(violation(scenario, trace))
        assert int(row["correct_outcome"]) == int(correct(scenario, trace))
        assert int(row["crashed"]) == int(trace.get("crash") is not None)
        for field in ("completed_tasks", "reassignments", "invalid_messages", "messages"):
            assert int(row[field]) == trace[field]
        assert float(row["wall_ms"]) == round(trace["wall_ms"], 5)
        traces[scenario, seed, variant] = trace
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    pairs = json.loads((folder / "paired.json").read_text(encoding="utf-8"))
    assert len(summary) == 2 * len(scenarios)
    assert len(pairs) == repeats * len(scenarios)
    for item in summary:
        group = [r for r in rows if r["scenario"] == item["scenario"]
                 and r["variant"] == item["variant"]]
        assert len(group) == item["runs"] == repeats
        assert item["class"] == known[item["scenario"]]["class"]
        for key, field in (("policy_violations", "policy_violation"),
                           ("correct_outcomes", "correct_outcome"), ("crashes", "crashed")):
            assert item[key] == sum(int(r[field]) for r in group)
        for key, field, digits in (("mean_wall_ms", "wall_ms", 5),
                                   ("mean_messages", "messages", 3),
                                   ("mean_reassignments", "reassignments", 3)):
            assert item[key] == round(statistics.mean(float(r[field]) for r in group), digits)
    for pair in pairs:
        name, seed = pair["scenario"], pair["seed"]
        left = next(r for r in rows if r["scenario"] == name and int(r["seed"]) == seed
                    and r["variant"] == "baseline")
        right = next(r for r in rows if r["scenario"] == name and int(r["seed"]) == seed
                     and r["variant"] == "protected")
        assert pair["violation_reduction"] == (int(left["policy_violation"])
                                                - int(right["policy_violation"]))
        assert pair["correct_outcome_gain"] == (int(right["correct_outcome"])
                                                - int(left["correct_outcome"]))
        assert pair["wall_delta_ms"] == round(float(right["wall_ms"])
                                               - float(left["wall_ms"]), 5)
        assert pair["message_delta"] == int(right["messages"]) - int(left["messages"])
    return {"verified": True, "scenarios": len(scenarios), "pairs": len(pairs),
            "traces": len(traces), "baseline_sha256": EXPECTED_BASELINE_SHA}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(json.dumps(verify(parser.parse_args().folder), indent=2))
