"""Paired, frozen-input baseline/negotiation comparison without paid APIs."""
from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess

from researchradar.coordination import research_stage2
from researchradar.frozen import load_frozen
from researchradar.negotiation import derive_checks, review_research

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/lab3/scenarios.json"
OUTPUT = ROOT / "run_output/lab3_experiments"
MODES = ("baseline", "negotiation")


def revision() -> tuple[str | None, str]:
    if not (ROOT / ".git").exists():
        return None, "unavailable_no_git_metadata"
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                                cwd=ROOT, capture_output=True, text=True, check=True, timeout=3)
        if status.stdout.strip():
            return None, "unavailable_dirty_checkout"
        reply = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                               cwd=ROOT, capture_output=True, text=True, check=True, timeout=3)
    except FileNotFoundError:
        return None, "unavailable_git_not_installed"
    except subprocess.CalledProcessError:
        return None, "unavailable_git_command_failed"
    except subprocess.TimeoutExpired:
        return None, "unavailable_git_timeout"
    commit = reply.stdout.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit):
        return None, "unavailable_invalid_git_response"
    return commit.lower(), "git_head"


def summarize(rows: list[dict], scenarios: list[dict]) -> list[dict]:
    result = []
    metrics = ("estimated_utility", "jain_normalized_satisfaction", "messages",
               "counteroffers", "arbitrations", "completed_checks", "denied_checks",
               "budget_violations", "slot_violations", "wall_ms", "negotiation_ms",
               "granted_units")
    for scenario in scenarios:
        for mode in MODES:
            group = [r for r in rows if r["scenario"] == scenario["name"] and r["mode"] == mode]
            if not group:
                continue
            item = {"scenario": scenario["name"], "mode": mode, "runs": len(group)}
            for key in metrics:
                values = [float(row[key]) for row in group]
                item[key + "_mean"] = round(statistics.mean(values), 5)
                item[key + "_sd"] = round(statistics.stdev(values), 5) if len(values) > 1 else 0.0
            result.append(item)
    return result


def paired(rows: list[dict], scenarios: list[dict]) -> list[dict]:
    result = []
    for scenario in scenarios:
        group = [x for x in rows if x["scenario"] == scenario["name"]]
        seeds = sorted({int(x["seed"]) for x in group})
        item = {"scenario": scenario["name"], "pairs": len(seeds)}
        for metric in ("estimated_utility", "jain_normalized_satisfaction",
                       "messages", "wall_ms", "completed_checks"):
            differences = []
            for seed in seeds:
                matches = {x["mode"]: x for x in group if int(x["seed"]) == seed}
                if set(matches) != set(MODES):
                    raise ValueError(f"unpaired result: {scenario['name']}/{seed}")
                differences.append(float(matches["negotiation"][metric])
                                   - float(matches["baseline"][metric]))
            item[metric + "_difference_mean"] = round(statistics.mean(differences), 5)
            item[metric + "_difference_sd"] = (round(statistics.stdev(differences), 5)
                                                    if len(differences) > 1 else 0)
            item[metric + "_difference_min"] = round(min(differences), 5)
            item[metric + "_difference_max"] = round(max(differences), 5)
        result.append(item)
    return result


def chart(summary: list[dict], scenarios: list[dict], metric: str,
          title: str, unit: str, path: Path) -> None:
    width, height = 1100, 440
    top = max(x[metric + "_mean"] for x in summary) * 1.2 or 1
    colors = {"baseline": "#31506b", "negotiation": "#b9603c"}
    labels = {"sufficient": "достаточно", "moderate_shortage": "умеренный дефицит",
              "strong_shortage": "сильный дефицит", "unequal_values": "разные ценности",
              "unresponsive_agent": "неответивший агент"}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="550" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{title}</text>',
             '<line x1="70" y1="355" x2="1080" y2="355" stroke="#333"/>',
             f'<text x="25" y="67" font-family="Arial" font-size="15">{unit}</text>']
    for index, scenario in enumerate(scenarios):
        left = 95 + index * 201
        for offset, mode in enumerate(MODES):
            value = next(x[metric + "_mean"] for x in summary
                         if x["scenario"] == scenario["name"] and x["mode"] == mode)
            bar = value / top * 260
            x = left + offset * 66
            parts.append(f'<rect x="{x}" y="{355-bar:.2f}" width="49" height="{bar:.2f}" fill="{colors[mode]}"/>')
            parts.append(f'<text x="{x+24}" y="{345-bar:.2f}" text-anchor="middle" font-family="Arial" font-size="13">{value:.2f}</text>')
        parts.append(f'<text x="{left+55}" y="384" text-anchor="middle" font-family="Arial" font-size="13">{labels[scenario["name"]]}</text>')
    parts.extend(['<rect x="360" y="408" width="14" height="14" fill="#31506b"/>',
                  '<text x="381" y="420" font-family="Arial" font-size="14">без переговоров</text>',
                  '<rect x="565" y="408" width="14" height="14" fill="#b9603c"/>',
                  '<text x="586" y="420" font-family="Arial" font-size="14">переговоры</text>',
                  '</svg>'])
    path.write_text("\n".join(parts), encoding="utf-8")


async def run(repeats: int, output: Path) -> None:
    scenarios = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len({x["name"] for x in scenarios}) != len(scenarios):
        raise ValueError("duplicate scenario")
    output.mkdir(parents=True, exist_ok=True)
    traces = output / "traces"
    traces.mkdir(exist_ok=True)
    research = await research_stage2("multi agent systems", load_frozen(),
                   mechanism="centralized", alternative="distributed task allocation")
    checks = derive_checks(research)
    rows, inputs = [], []
    for scenario_number, scenario in enumerate(scenarios):
        for seed in range(repeats):
            rng = random.Random(scenario_number * 100_000 + seed)
            adjusted = []
            for check in checks:
                full = float(scenario.get(check.owner + "_full_value", check.full_value))
                partial = float(scenario.get(check.owner + "_partial_value", check.partial_value))
                adjusted.append(replace(check,
                    full_value=round(full * rng.uniform(0.97, 1.03), 5),
                    partial_value=round(partial * rng.uniform(0.97, 1.03), 5)))
            delay = round(2 * rng.uniform(0.9, 1.1), 5)
            input_row = {"scenario": scenario["name"], "seed": seed,
                         "credits": scenario["credits"], "delay_ms": delay,
                         "silent_owners": scenario["silent_owners"],
                         "checks": [{"id": x.id, "owner": x.owner,
                                     "full_value": x.full_value,
                                     "partial_value": x.partial_value,
                                     "public_priority": x.public_priority,
                                     "full_units": x.full_units, "min_units": x.min_units}
                                    for x in adjusted]}
            inputs.append(input_row)
            for mode in MODES:
                result = await review_research(research, mode=mode,
                    credits=scenario["credits"], checks=tuple(adjusted),
                    silent_owners=frozenset(scenario["silent_owners"]),
                    delay_ms=delay, timeout=0.03)
                metrics = result["metrics"]
                row = {"scenario": scenario["name"], "seed": seed, "mode": mode,
                       "credits": scenario["credits"], "requested_units": metrics["requested_units"],
                       "spent_units": result["resource"]["spent"],
                       "held_units": result["resource"]["held"],
                       "plan": json.dumps(result["plan"], sort_keys=True)}
                row.update({key: round(value, 5) if isinstance(value, float) else value
                            for key, value in metrics.items() if key != "message_kinds"})
                rows.append(row)
                if seed == 0:
                    (traces / f"{scenario['name']}-{mode}.json").write_text(
                        json.dumps([{key: x[key] for key in (
                            "elapsed_ms", "sender", "recipient", "kind", "check_id",
                            "round", "units", "reason")}
                            for x in result["trace"]], ensure_ascii=False, indent=2),
                        encoding="utf-8")
    with (output / "raw.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows, scenarios)
    (output / "inputs.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "paired.json").write_text(json.dumps(paired(rows, scenarios), ensure_ascii=False, indent=2), encoding="utf-8")
    commit, commit_source = revision()
    metadata = {"version": "lab3-v1.0", "version_source": "script_constant",
                "code_commit_at_run": commit, "code_commit_source": commit_source,
                "frozen_sha256": sha256((ROOT / "data/frozen_sources.json").read_bytes()).hexdigest(),
                "scenarios_sha256": sha256(CONFIG.read_bytes()).hexdigest(),
                "research_materials_sha256": sha256(json.dumps(research["materials"],
                    ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "data_kind": "synthetic_fixture", "search_allocation": "centralized",
                "modes": MODES, "scenarios": [x["name"] for x in scenarios],
                "repeats": repeats, "seeds": list(range(repeats)), "runs": len(rows),
                "python_version": platform.python_version(), "platform": platform.platform(),
                "time_note": "Wall time includes OS scheduling; delay_ms is a controlled synthetic verification delay; check_ms_sum can overlap across agents."}
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    chart(summary, scenarios, "estimated_utility", "Оценочная полезность проверок",
          "условные единицы", output / "utility.svg")
    chart(summary, scenarios, "jain_normalized_satisfaction", "Нормированная удовлетворённость",
          "индекс Джейна", output / "fairness.svg")
    chart(summary, scenarios, "messages", "Сообщения протокола проверки",
          "сообщения", output / "messages.svg")
    chart(summary, scenarios, "wall_ms", "Время проверки",
          "мс, wall-clock", output / "wall_time.svg")
    print(f"{len(rows)} runs; {len(scenarios)} scenarios; {repeats} paired repeats: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("repeats must be 1..100")
    asyncio.run(run(args.repeats, args.output))
