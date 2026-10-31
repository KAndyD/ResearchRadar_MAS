"""Paired, offline fault injection against frozen lab3-v1.1 and current code."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "experiments/lab4/baseline_lab3_v1.1.zip"
SCENARIOS = ROOT / "experiments/lab4/scenarios.json"
EXPECTED_BASELINE_SHA = "da223cc3ff29e0a0842c159270c4697ca3d5960d0359e6388119de8f56caaa2a"


def violation(scenario: str, result: dict) -> bool:
    if scenario in {"wrong_run_result", "source_mismatch"}:
        return bool(result["accepted_fault_material"])
    if scenario == "malformed_result":
        return result["crash"] is not None
    if scenario == "forged_shutdown":
        return result["reassignments"] > 0
    if scenario == "malicious_bid":
        return result["assignments"].get("oa-primary", [None])[0] == "scholar_b"
    if scenario in {"forbidden_delegate", "resource_owner"}:
        return bool(result["accepted_forbidden"])
    return False


def correct(scenario: str, result: dict) -> bool:
    if violation(scenario, result) or result.get("crash"):
        return False
    if scenario in {"forbidden_delegate", "resource_owner"}:
        return not result["accepted_forbidden"] and (
            scenario != "resource_owner" or result["resource"]["spent"] == 2)
    if scenario == "source_429":
        return result["completed_tasks"] == 3 and "ax-preprints" in result["errors"]
    return result["completed_tasks"] == 4 and not result["errors"]


def code_revision() -> tuple[str | None, str]:
    if not (ROOT / ".git").exists():
        return None, "unavailable_no_git_metadata"
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--", "src/researchradar",
             "tools/lab4_probe.py", "tools/run_lab4_experiments.py",
             "experiments/lab4/scenarios.json", "experiments/lab4/baseline_lab3_v1.1.zip"],
             cwd=ROOT, capture_output=True, text=True, timeout=5, check=True)
        if status.stdout.strip():
            return None, "unavailable_dirty_experiment_inputs"
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        return (sha, "git_clean_experiment_inputs") if len(sha) == 40 else (
            None, "unavailable_invalid_git_sha")
    except (OSError, subprocess.SubprocessError):
        return None, "unavailable_git_error"


def run(repeats: int, output: Path) -> dict:
    if repeats < 1 or repeats > 50:
        raise ValueError("repeats must be 1..50")
    baseline_sha = sha256(BASELINE.read_bytes()).hexdigest()
    if baseline_sha != EXPECTED_BASELINE_SHA:
        raise RuntimeError("historical baseline snapshot changed")
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in scenarios:
        name = scenario["id"]
        for seed in range(repeats):
            for variant in ("baseline", "protected"):
                trace_path = output / "traces" / f"{name}-{seed}-{variant}.json"
                env = os.environ.copy()
                env.pop("OPENROUTER_API_KEY", None)
                env["PYTHONPATH"] = str(BASELINE if variant == "baseline"
                                        else ROOT / "src")
                command = [sys.executable, str(ROOT / "tools/lab4_probe.py"),
                           name, "--seed", str(seed), "--output", str(trace_path)]
                done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                      text=True, timeout=15)
                if done.returncode:
                    raise RuntimeError(f"probe failed {name}/{seed}/{variant}: "
                                       + done.stderr[-600:])
                result = json.loads(trace_path.read_text(encoding="utf-8"))
                origin = result.pop("module_path")
                if variant == "baseline" and "baseline_lab3_v1.1.zip" not in origin:
                    raise RuntimeError("baseline did not import the historical snapshot")
                if variant == "protected" and "baseline_lab3_v1.1.zip" in origin:
                    raise RuntimeError("protected run imported baseline")
                result.update({"variant": variant, "module_origin":
                               "historical_snapshot" if variant == "baseline" else
                               "current_src"})
                trace_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                                      + "\n", encoding="utf-8")
                row = {"scenario": name, "class": scenario["class"], "seed": seed,
                       "variant": variant, "policy_violation": int(violation(name, result)),
                       "correct_outcome": int(correct(name, result)),
                       "crashed": int(result.get("crash") is not None),
                       "completed_tasks": result.get("completed_tasks", 0),
                       "reassignments": result.get("reassignments", 0),
                       "invalid_messages": result.get("invalid_messages", 0),
                       "messages": result.get("messages", len(result.get("trace", []))),
                       "wall_ms": round(result["wall_ms"], 5),
                       "trace": trace_path.relative_to(output).as_posix()}
                rows.append(row)
    with (output / "raw.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    pairs = []
    for scenario in scenarios:
        name = scenario["id"]
        group = [x for x in rows if x["scenario"] == name]
        for variant in ("baseline", "protected"):
            subset = [x for x in group if x["variant"] == variant]
            summary.append({"scenario": name, "class": scenario["class"],
                "variant": variant, "runs": len(subset),
                "policy_violations": sum(x["policy_violation"] for x in subset),
                "correct_outcomes": sum(x["correct_outcome"] for x in subset),
                "crashes": sum(x["crashed"] for x in subset),
                "mean_wall_ms": round(statistics.mean(x["wall_ms"] for x in subset), 5),
                "mean_messages": round(statistics.mean(x["messages"] for x in subset), 3),
                "mean_reassignments": round(statistics.mean(x["reassignments"] for x in subset), 3)})
        by_seed = {seed: {x["variant"]: x for x in group if x["seed"] == seed}
                   for seed in range(repeats)}
        for seed, pair in by_seed.items():
            pairs.append({"scenario": name, "seed": seed,
                "violation_reduction": pair["baseline"]["policy_violation"] -
                                       pair["protected"]["policy_violation"],
                "correct_outcome_gain": pair["protected"]["correct_outcome"] -
                                        pair["baseline"]["correct_outcome"],
                "wall_delta_ms": round(pair["protected"]["wall_ms"] -
                                       pair["baseline"]["wall_ms"], 5),
                "message_delta": pair["protected"]["messages"] -
                                 pair["baseline"]["messages"]})
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                        encoding="utf-8")
    (output / "paired.json").write_text(json.dumps(pairs, indent=2) + "\n",
                                       encoding="utf-8")
    revision, revision_source = code_revision()
    metadata = {"version": "lab4-v1.0", "baseline_tag": "lab3-v1.1",
                "baseline_sha256": baseline_sha, "protected_code_commit": revision,
                "protected_code_commit_source": revision_source,
                "scenarios_sha256": sha256(SCENARIOS.read_bytes()).hexdigest(),
                "repeats": repeats, "scenario_count": len(scenarios),
                "runs": len(rows), "python": sys.version.split()[0],
                "network_and_paid_llm_calls": 0,
                "timing_note": "wall_ms includes process startup and OS scheduling; "
                               "paired order is fixed baseline then protected"}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n",
                                         encoding="utf-8")
    print(f"{len(rows)} runs, {len(pairs)} pairs, {len(scenarios)} scenarios: {output}")
    return {"rows": rows, "summary": summary, "pairs": pairs, "metadata": metadata}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("run_output/lab4_experiments"))
    args = parser.parse_args()
    run(args.repeats, args.output)


if __name__ == "__main__":
    main()
