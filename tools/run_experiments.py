"""Paired, frozen-data comparison of centralized and Contract Net allocation."""
from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import random
import statistics
import subprocess

from researchradar.coordination import WorkerSpec, default_workers, research_stage2
from researchradar.frozen import load_frozen

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
QUESTION = "multi agent systems"
ALTERNATIVE = "distributed task allocation"
SCENARIOS = ("balanced", "hidden_load", "limited_availability", "source_failure")
METHODS = ("centralized", "contract-net")


class FailingSource:
    def search(self, query: str, limit: int):
        raise RuntimeError("controlled source outage")


def workload(name: str, seed: int) -> tuple[dict, tuple[WorkerSpec, ...]]:
    if name not in SCENARIOS:
        raise ValueError(name)
    sources = load_frozen()
    rng = random.Random(seed)
    specs = []
    for item in default_workers():
        private = 2 if name == "hidden_load" and item.name in {"scholar_a", "news_a"} else 0
        available = not (name == "limited_availability" and item.name in {"scholar_a", "news_a"})
        actual = {kind: round(ms * (1 + private) * rng.uniform(0.9, 1.1), 3)
                  for kind, ms in item.actual_ms.items()}
        specs.append(replace(item, private_load=private, available=available, actual_ms=actual))
    if name == "source_failure":
        sources["arxiv"] = FailingSource()
    return sources, tuple(specs)


def describe_trace(trace: list[dict]) -> list[dict]:
    return [{key: item[key] for key in ("elapsed_ms", "sender", "recipient", "kind", "task_id")}
            for item in trace]


def summarize(rows: list[dict]) -> list[dict]:
    groups = {(s, m): [r for r in rows if r["scenario"] == s and r["mechanism"] == m]
              for s in SCENARIOS for m in METHODS}
    summary = []
    for (scenario, mechanism), group in groups.items():
        if not group:
            continue
        item = {"scenario": scenario, "mechanism": mechanism, "runs": len(group)}
        for key in ("wall_ms", "coordination_ms", "messages", "completed_tasks",
                    "reassignments", "scientific_records", "news_records", "load_std"):
            values = [float(r[key]) for r in group]
            item[key + "_mean"] = round(statistics.mean(values), 5)
            item[key + "_sd"] = round(statistics.stdev(values), 5) if len(values) > 1 else 0.0
        summary.append(item)
    return summary


def paired_differences(rows: list[dict]) -> list[dict]:
    """Contract Net minus centralized under identical scenario and seed."""
    result = []
    for scenario in SCENARIOS:
        group = [r for r in rows if r["scenario"] == scenario]
        seeds = sorted({int(r["seed"]) for r in group})
        item = {"scenario": scenario, "pairs": len(seeds)}
        for metric in ("wall_ms", "coordination_ms", "messages", "completed_tasks"):
            values = []
            for seed in seeds:
                pair = {r["mechanism"]: r for r in group if int(r["seed"]) == seed}
                if set(pair) != set(METHODS):
                    raise ValueError(f"unpaired experiment: {scenario}/{seed}")
                values.append(float(pair["contract-net"][metric]) - float(pair["centralized"][metric]))
            item[metric + "_difference_mean"] = round(statistics.mean(values), 5)
            item[metric + "_difference_sd"] = round(statistics.stdev(values), 5) if len(values) > 1 else 0.0
            item[metric + "_difference_min"] = round(min(values), 5)
            item[metric + "_difference_max"] = round(max(values), 5)
        result.append(item)
    return result


def chart(summary: list[dict], metric: str, title: str, unit: str, output: Path) -> None:
    # Editable vector chart; values are read directly from summary derived from raw.csv.
    width, height = 1050, 430
    values = [r[metric + "_mean"] for r in summary]
    top = max(values) * 1.18 if values else 1
    colors = {"centralized": "#304b68", "contract-net": "#bc6540"}
    labels = {"balanced": "равномерная", "hidden_load": "скрытая загрузка",
              "limited_availability": "ограниченный состав", "source_failure": "отказ источника"}
    esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;"))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="525" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{esc(title)}</text>',
             '<line x1="85" y1="355" x2="1010" y2="355" stroke="#333"/>',
             f'<text x="35" y="65" font-family="Arial" font-size="15">{esc(unit)}</text>']
    for i, scenario in enumerate(SCENARIOS):
        left = 120 + i * 225
        for j, mechanism in enumerate(METHODS):
            row = next(r for r in summary if r["scenario"] == scenario and r["mechanism"] == mechanism)
            value = row[metric + "_mean"]
            bar_height = 255 * value / top if top else 0
            x = left + j * 72
            y = 355 - bar_height
            parts.append(f'<rect x="{x}" y="{y:.2f}" width="55" height="{bar_height:.2f}" fill="{colors[mechanism]}"/>')
            parts.append(f'<text x="{x+27}" y="{y-8:.2f}" text-anchor="middle" font-family="Arial" font-size="14">{value:.2f}</text>')
        parts.append(f'<text x="{left+63}" y="383" text-anchor="middle" font-family="Arial" font-size="14">{esc(labels[scenario])}</text>')
    parts.extend(['<rect x="320" y="400" width="14" height="14" fill="#304b68"/>',
                  '<text x="342" y="412" font-family="Arial" font-size="14">централизованное</text>',
                  '<rect x="520" y="400" width="14" height="14" fill="#bc6540"/>',
                  '<text x="542" y="412" font-family="Arial" font-size="14">контрактная сеть</text>',
                  '</svg>'])
    output.write_text("\n".join(parts), encoding="utf-8")


async def run(repeats: int, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    trace_dir = output / "traces"
    trace_dir.mkdir(exist_ok=True)
    rows = []
    frozen_hash = sha256((ROOT / "data/frozen_sources.json").read_bytes()).hexdigest()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for scenario in SCENARIOS:
        for seed in range(repeats):
            for mechanism in METHODS:
                sources, workers = workload(scenario, seed)
                result = await research_stage2(QUESTION, sources,
                    mechanism=mechanism, alternative=ALTERNATIVE, workers=workers,
                    bid_timeout=0.15, task_timeout=0.5, deadline_seconds=5)
                metrics = result["metrics"]
                loads = [state["handled"] for state in result["agents"].values()]
                rows.append({"scenario": scenario, "seed": seed, "mechanism": mechanism,
                    "agent_count": len(workers), "task_count": metrics["task_count"],
                    "wall_ms": round(metrics["wall_seconds"] * 1000, 5),
                    "coordination_ms": round(metrics["coordination_seconds"] * 1000, 5),
                    "messages": metrics["messages"],
                    "completed_tasks": metrics["completed_tasks"],
                    "reassignments": metrics["reassignments"],
                    "scientific_records": len(result["materials"]["scientific"]),
                    "news_records": len(result["materials"]["news"]),
                    "load_std": round(statistics.pstdev(loads), 5),
                    "errors": json.dumps(result["errors"], ensure_ascii=False)})
                if seed == 0:
                    (trace_dir / f"{scenario}-{mechanism}.json").write_text(
                        json.dumps(describe_trace(result["trace"]), ensure_ascii=False, indent=2),
                        encoding="utf-8")
    with (output / "raw.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "paired.json").write_text(json.dumps(paired_differences(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"version": "lab2-v1.0-candidate", "code_commit_at_run": commit,
                "question": QUESTION, "alternative": ALTERNATIVE,
                "data_kind": "synthetic_fixture", "frozen_sha256": frozen_hash,
                "scenarios": SCENARIOS, "seeds": list(range(repeats)),
                "mechanisms": METHODS, "runs": len(rows), "agents_per_run": 6,
                "tasks_per_run": 5, "time_note": "wall and cumulative coordination measured with perf_counter; worker service delays are controlled synthetic milliseconds; actual thread scheduling contributes to wall time"}
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    chart(summary, "messages", "Сообщения протокола", "сообщений", output / "messages.svg")
    chart(summary, "wall_ms", "Время исследования", "мс, wall-clock", output / "wall_time.svg")
    chart(summary, "coordination_ms", "Сумма задержек назначения", "мс, по задачам", output / "coordination.svg")
    print(f"{len(rows)} paired runs: {output / 'raw.csv'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--output", type=Path, default=RESULTS)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("repeats must be 1..100")
    asyncio.run(run(args.repeats, args.output))
