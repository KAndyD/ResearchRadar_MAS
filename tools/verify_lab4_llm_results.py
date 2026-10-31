"""Check mock-output aggregates and replay the stored live Qwen response."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from researchradar.evidence_analysis_v1 import EvidenceError, context_sha256, validate_response


ROOT = Path(__file__).resolve().parents[1]


def verify(folder: Path) -> dict:
    with (folder / "raw.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["cases_sha256"] == sha256((ROOT / "experiments/lab4/llm_cases.json").read_bytes()).hexdigest()
    assert metadata["fixture_sha256"] == sha256((ROOT / "data/lab4_fixture_analysis.json").read_bytes()).hexdigest()
    assert metadata["historical_comparison"] is False
    assert len(rows) == summary["cases"] == 8
    assert len({row["scenario"] for row in rows}) == len(rows)
    for row in rows:
        trace_path = (folder / row["trace"]).resolve()
        assert trace_path.is_relative_to(folder.resolve())
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["scenario"] == row["scenario"] and trace["kind"] == row["kind"]
        assert trace["model_mode"] == "authored_mock_response"
        assert int(row["calls"]) == trace["calls"] == 1
        assert int(row["minimal_parse_accepts"]) == int(trace["minimal_parse_accepts"])
        assert int(row["validated_accepts"]) == int(trace["validator_status"] == "accepted")
        assert int(row["unsafe_accept"]) == int(not int(row["expected_accept"]) and int(row["validated_accepts"]))
        assert int(row["false_positive"]) == int(int(row["expected_accept"]) and not int(row["validated_accepts"]))
        assert trace["resource_or_system_action_executed"] is False
    assert summary["normal_cases"] == sum(r["kind"] == "normal" for r in rows)
    assert summary["adversarial_cases"] == sum(r["kind"] == "adversarial" for r in rows)
    assert summary["minimal_parser_unsafe_accepts"] == sum(
        int(r["minimal_parse_accepts"]) and not int(r["expected_accept"]) for r in rows)
    assert summary["validator_unsafe_accepts"] == sum(int(r["unsafe_accept"]) for r in rows)
    assert summary["false_positives"] == sum(int(r["false_positive"]) for r in rows)
    assert summary["actual_provider_calls"] == 0
    live = json.loads((ROOT / "experiments/lab4/live_qwen_evidence.json").read_text(encoding="utf-8"))
    assert live["origin"] == "one_live_qwen_call_on_live_search"
    assert live["recorded_response"]["origin"] == "live_qwen"
    assert live["recorded_response"]["context_sha256"] == context_sha256(live["context"])
    try:
        validate_response(live["recorded_response"]["response"], live["context"])
    except EvidenceError as exc:
        assert str(exc) == live["validation_after_rule_fix"]["reason"] == "ungrounded_scientific_evidence"
    else:
        raise AssertionError("stored live response unexpectedly accepted")
    return {"verified": True, "mock_cases": len(rows), "live_calls": 1,
            "live_rejection": "ungrounded_scientific_evidence"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(json.dumps(verify(parser.parse_args().folder), indent=2))
