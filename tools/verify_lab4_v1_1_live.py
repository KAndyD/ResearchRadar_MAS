"""Replay every paid version 2 response without another provider call."""
from __future__ import annotations

import json
from pathlib import Path

from researchradar.evidence_analysis import EvidenceError, context_sha256, validate_response


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/lab4_v1_1"
EXPECTED = ("related_real_pair", "unrelated_real_pair", "metadata_only_real_pair")


def verify() -> dict:
    totals = []
    for round_name, expected_status in (("live", "rejected"),
                                        ("live_round2", "usable_preliminary")):
        directory = FOLDER / round_name
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        assert summary["calls_attempted"] == summary["calls_recorded"] == 3
        assert {x["case"] for x in summary["cases"]} == set(EXPECTED)
        cost = 0.0
        for name in EXPECTED:
            row = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
            recorded = json.loads((directory / f"{name}_response.json").read_text(
                encoding="utf-8"))
            assert row["case"] == name and row["response"] == recorded
            assert recorded["schema_version"] == 2 and recorded["origin"] == "live_qwen"
            assert recorded["context_sha256"] == context_sha256(row["context"])
            assert row["expense_delta"]["calls"] == 1
            cost += row["expense_delta"]["actual_usd"]
            try:
                analysis = validate_response(recorded["response"], row["context"])
            except EvidenceError as exc:
                assert expected_status == "rejected"
                assert str(exc) == row["result"]["reason"] == "invalid_explanation"
            else:
                assert expected_status == "usable_preliminary"
                assert analysis == row["result"]["analysis"]
                assert analysis["claim_support"] == "not_assessed"
                assert analysis["news_claim_verification"] == "not_performed"
        assert round(cost, 9) == summary["actual_usd"]
        assert summary["usable_preliminary"] == (0 if round_name == "live" else 3)
        totals.append(summary)
    review = json.loads((FOLDER / "live_manual_review.json").read_text(encoding="utf-8"))
    assert {x["case"] for x in review["cases"]} == set(EXPECTED)
    return {"verified": True, "calls": 6, "first_round_rejected": 3,
            "second_round_usable": 3,
            "actual_usd": round(sum(x["actual_usd"] for x in totals), 9)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
