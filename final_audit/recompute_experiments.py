"""Independently recompute saved experiment aggregates from canonical ZIP extractions."""
from __future__ import annotations

import csv
from collections import defaultdict
import json
from math import isclose
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[1]
LOG = json.loads((ROOT / "run_output/final_audit_execution_raw.json").read_text(encoding="utf-8"))
BASE = Path(LOG["workspace"])
CONFIG = {
    "lab2-v1.1": ("experiments/results", "mechanism", "centralized", "contract-net", 4, 12),
    "lab3-v1.1": ("experiments/lab3/results", "mode", "baseline", "negotiation", 5, 12),
    "lab4-v1.1": ("experiments/lab4/results", "variant", "baseline", "protected", 10, 5),
}


def same(actual: float, expected: float) -> bool:
    return isclose(actual, expected, rel_tol=0, abs_tol=0.000021)


def main() -> None:
    output = {}
    for tag, (relative, variant_key, first, second, scenarios, repeats) in CONFIG.items():
        folder = BASE / tag / relative
        rows = list(csv.DictReader((folder / "raw.csv").open(encoding="utf-8", newline="")))
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        paired = json.loads((folder / "paired.json").read_text(encoding="utf-8"))
        scenario_names = {r["scenario"] for r in rows}
        assert len(scenario_names) == scenarios
        assert len(rows) == scenarios * repeats * 2
        groups = defaultdict(list)
        pair_rows = defaultdict(dict)
        for row in rows:
            groups[(row["scenario"], row[variant_key])].append(row)
            key = (row["scenario"], int(row["seed"]))
            assert row[variant_key] not in pair_rows[key]
            pair_rows[key][row[variant_key]] = row
        assert len(pair_rows) == scenarios * repeats
        assert all(set(pair) == {first, second} for pair in pair_rows.values())
        assert all(len(group) == repeats for group in groups.values())
        checked = 0
        if tag != "lab4-v1.1":
            for item in summary:
                subset = groups[(item["scenario"], item[variant_key])]
                assert item["runs"] == repeats
                for field, expected in item.items():
                    if field.endswith("_mean"):
                        values = [float(r[field[:-5]]) for r in subset]
                        assert same(mean(values), float(expected)), (tag, field, item["scenario"])
                        checked += 1
                    elif field.endswith("_sd"):
                        values = [float(r[field[:-3]]) for r in subset]
                        assert same(stdev(values), float(expected)), (tag, field, item["scenario"])
                        checked += 1
            for item in paired:
                assert item["pairs"] == repeats
                pairs = [pair for (scenario, _), pair in pair_rows.items() if scenario == item["scenario"]]
                for field, expected in item.items():
                    marker = "_difference_"
                    if marker not in field:
                        continue
                    measure, statistic = field.split(marker)
                    diffs = [float(p[second][measure]) - float(p[first][measure]) for p in pairs]
                    actual = {"mean": mean, "sd": stdev, "min": min, "max": max}[statistic](diffs)
                    assert same(actual, float(expected)), (tag, field, item["scenario"])
                    checked += 1
        else:
            assert len(summary) == scenarios * 2
            assert len(paired) == scenarios * repeats
            for item in summary:
                subset = groups[(item["scenario"], item["variant"])]
                checks = {
                    "runs": len(subset),
                    "policy_violations": sum(int(r["policy_violation"]) for r in subset),
                    "correct_outcomes": sum(int(r["correct_outcome"]) for r in subset),
                    "crashes": sum(int(r["crashed"]) for r in subset),
                    "mean_wall_ms": mean(float(r["wall_ms"]) for r in subset),
                    "mean_messages": mean(int(r["messages"]) for r in subset),
                    "mean_reassignments": mean(int(r["reassignments"]) for r in subset),
                }
                for field, actual in checks.items():
                    assert same(actual, float(item[field])), (tag, field, item["scenario"])
                    checked += 1
            for item in paired:
                pair = pair_rows[(item["scenario"], int(item["seed"]))]
                expected = {
                    "violation_reduction": int(pair[first]["policy_violation"]) - int(pair[second]["policy_violation"]),
                    "correct_outcome_gain": int(pair[second]["correct_outcome"]) - int(pair[first]["correct_outcome"]),
                    "wall_delta_ms": float(pair[second]["wall_ms"]) - float(pair[first]["wall_ms"]),
                    "message_delta": int(pair[second]["messages"]) - int(pair[first]["messages"]),
                }
                for field, actual in expected.items():
                    assert same(actual, float(item[field])), (tag, field, item["scenario"])
                    checked += 1
            for row in rows:
                assert (folder / row["trace"]).is_file(), (tag, row["trace"])
        record = {"rows": len(rows), "scenarios": scenarios, "paired_seed_groups": len(pair_rows),
                  "aggregate_values_recomputed": checked, "summary_rows": len(summary),
                  "paired_rows": len(paired)}
        if tag == "lab4-v1.1":
            record["policy_violations"] = {v: sum(int(r["policy_violation"]) for r in rows if r[variant_key] == v)
                                            for v in (first, second)}
            record["correct_outcomes"] = {v: sum(int(r["correct_outcome"]) for r in rows if r[variant_key] == v)
                                          for v in (first, second)}
            record["crashes"] = {v: sum(int(r["crashed"]) for r in rows if r[variant_key] == v)
                                 for v in (first, second)}
        output[tag] = record
        print(tag, record)
    (ROOT / "final_audit/experiment_recalculation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
