"""Independently replay and recalculate the corrected LLM experiment."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from researchradar.evidence_analysis import EvidenceError, context_sha256, validate_response


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "experiments/lab4_v1_1/cases.json"


def verify(folder: Path) -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    by_name = {x["id"]: x for x in cases}
    with (folder / "raw.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert len(rows) == len(cases) == summary["cases"]
    assert len(by_name) == len(cases)
    assert metadata["schema_version"] == 2
    assert metadata["cases_sha256"] == sha256(CASES.read_bytes()).hexdigest()
    assert metadata["network_and_paid_calls"] == 0
    for row in rows:
        expected = by_name[row["scenario"]]
        assert row["class"] == expected["class"]
        assert row["expected_status"] == expected["expected_status"]
        trace_path = (folder / row["trace"]).resolve()
        assert trace_path.is_relative_to(folder.resolve())
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["scenario"] == row["scenario"]
        assert trace["context_sha256"] == context_sha256(trace["context"])
        assert trace["provider_calls"] == 1 and trace["paid_calls"] == 0
        assert trace["program_action_executed"] is False
        if trace["response"] is None:
            assert row["scenario"] == "provider_timeout"
            status = "unavailable"
        else:
            assert trace["response_sha256"] == sha256(trace["response"].encode()).hexdigest()
            try:
                replayed = validate_response(trace["response"], trace["context"])
            except EvidenceError:
                status, replayed = "rejected", None
            else:
                status = "usable_preliminary"
        assert status == row["actual_status"] == trace["result"]["status"]
        assert int(row["correct"]) == int(status == expected["expected_status"])
        assert int(row["verified_claims"]) == 0
        if replayed:
            assert replayed["claim_support"] == "not_assessed"
            assert replayed["news_claim_verification"] == "not_performed"
            for kind in ("scientific", "news"):
                evidence = replayed[f"{kind}_evidence"]
                if evidence:
                    assert evidence["verification"] == "exact_source_excerpt"
    unsupported = json.loads((folder / "traces/unsupported_claim_real_excerpt.json").read_text(
        encoding="utf-8"))
    assert unsupported["legacy_unsupported_claim_accepted"] is True
    assert unsupported["result"]["analysis"]["claim_support"] == "not_assessed"
    assert summary["correct"] == sum(int(r["correct"]) for r in rows)
    assert summary["normal"] == sum(r["class"] == "normal" for r in rows)
    assert summary["normal_usable"] == sum(r["class"] == "normal" and
                                           r["actual_status"] == "usable_preliminary"
                                           for r in rows)
    assert summary["unsupported_claim_verified"] == 0
    assert summary["actual_provider_calls"] == 0
    return {"verified": True, "cases": len(rows), "normal_usable": summary["normal_usable"],
            "unsupported_claim_verified": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(json.dumps(verify(parser.parse_args().folder), indent=2))
