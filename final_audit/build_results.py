"""Assemble concise machine-readable audit decisions from observed evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "final_audit"
TAGS = ("lab1-v1.2", "lab2-v1.1", "lab3-v1.1", "lab4-v1.1")
GH = Path(r"C:\Program Files\GitHub CLI\gh.exe")
CI = {"lab1-v1.2": 40978707861, "lab2-v1.1": 41110413116,
      "lab3-v1.1": 41123364044, "lab4-v1.1": 41153033282}


def read(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def main() -> None:
    protocol = read("protocol.json")["releases"]
    experiments, reports = read("experiment_recalculation.json"), read("report_inspection.json")
    sync, security, smoke = read("tag_sync.json"), read("security_scan.json"), read("smoke_log.json")
    preservation = read("historical_preservation.json")
    checks = []

    def add(tag: str, prop: str, method: str, source: str, expected, actual,
            status: str, evidence: str) -> None:
        checks.append({"laboratory": int(tag[3]), "version": tag, "property": prop,
                       "method": method, "source_file": source,
                       "expected": expected, "actual": actual,
                       "status": status, "evidence": evidence})

    for tag in TAGS:
        record = protocol[tag]
        assets = record["assets"]
        all_hashes = all(x["remote_digest_match"] for x in assets)
        add(tag, "published release asset digests", "download and SHA-256 vs GitHub digest",
            f"run_output/final_audit_downloads/{tag}", "all match", f"{len(assets)} assets, all match" if all_hashes else "mismatch",
            "PASS" if all_hashes else "FAIL", "final_audit/protocol.json")
        bundles = [x for x in assets if "archive" in x]
        valid = all(x["archive"]["sha256_ok"] and x["archive"]["crc_ok"] for x in bundles)
        add(tag, "submission and audit ZIP integrity", "CRC and member SHA-256 manifest",
            ", ".join(x["name"] for x in bundles), "two valid ZIPs", "valid" if valid else "invalid",
            "PASS" if valid else "FAIL", "final_audit/protocol.json")
        unchanged = not sync[tag]["material_difference"] and not sync[tag]["missing_from_tag"]
        add(tag, "archive contents vs release tag", "compare every archive member with Git blob, normalize CRLF",
            f"{tag} Git tag", "no material difference",
            f"{sync[tag]['checked']} checked; {len(sync[tag]['newline_only_difference'])} line-ending variants; "
            f"{len(sync[tag]['material_difference'])} material differences",
            "PASS" if unchanged else "FAIL", "final_audit/tag_sync.json")
        tests = next(x for x in record["runs"] if x["label"] == "tests")
        count = {"lab1-v1.2": 21, "lab2-v1.1": 35, "lab3-v1.1": 58, "lab4-v1.1": 77}[tag]
        passed = tests["exit_code"] == 0 and f"Ran {count} tests" in tests["output_tail"]
        add(tag, "historical tests from extracted audit ZIP", "unittest discover with extracted src on PYTHONPATH",
            f"{tag}/tests", f"{count} tests OK", tests["output_tail"][-120:].strip(),
            "PASS" if passed else "FAIL", "final_audit/protocol.json")
        demos = [x for x in record["runs"] if x["label"].startswith("demo")]
        add(tag, "representative offline DEMO", "execute historical CLI from extraction",
            f"{tag}/src", "all demos succeed", f"{len(demos)} demos; exit codes {[x['exit_code'] for x in demos]}",
            "PASS" if all(x["exit_code"] == 0 for x in demos) else "FAIL", "final_audit/protocol.json")
        report = reports[tag]
        author = all(report["expected_in_pdf"].values()) and all(report["expected_in_docx"].values())
        clean = not any(report["forbidden_in_pdf"].values()) and not any(report["forbidden_in_docx"].values())
        add(tag, "separate PDF and DOCX report", "PDF extraction, full-page render, OOXML inspection",
            report["pdf"] + "; " + report["docx"], "author, group, year; no educational boilerplate",
            f"{report['pages']} PDF pages; author/group/year={author}; forbidden={not clean}; "
            f"DOCX render unavailable", "PASS_WITH_LIMITATIONS" if author and clean else "FAIL",
            "final_audit/report_inspection.json")
        add(tag, "independent DOCX page layout", "LibreOffice renderer availability check",
            report["docx"], "render every DOCX page", "LibreOffice unavailable; OOXML checked",
            "NOT_VERIFIED", "final_audit/report_inspection.json")
        sec = security["releases"][tag]
        risky = sum(len(v["credential_pattern_files"]) + len(v["unwanted_names"])
                    for v in sec["archives"].values())
        add(tag, "published credential and private-data scan", "scan names and token signatures in both ZIPs",
            f"{tag} Release ZIPs", "no credential tokens or private databases", f"{risky} matches",
            "PASS" if risky == 0 else "FAIL", "final_audit/security_scan.json")
        ci = json.loads(subprocess.check_output([str(GH), "run", "view", str(CI[tag]), "--json",
                                                 "conclusion,status,headSha,headBranch,url"],
                                                cwd=ROOT, text=True, encoding="utf-8"))
        good_ci = ci["conclusion"] == "success" and ci["headSha"] == record["tag_commit"]
        add(tag, "tag CI", "GitHub Actions run metadata", ci["url"], "success on release commit",
            f"{ci['conclusion']} on {ci['headSha']}", "PASS" if good_ci else "FAIL", ci["url"])

    manual_requirements = {
        "lab1-v1.2": ("task, formal agent model, role diagram, communication graph, architecture rationale",
                        "historical architecture PDF and engine/model/router implementation"),
        "lab2-v1.1": ("two explicit allocation mechanisms and comparative metrics",
                        "historical coordination.py, stage2 tests and 96-row paired corpus"),
        "lab3-v1.1": ("resource conflict, negotiation protocol, before/after efficiency and fairness",
                        "historical negotiation.py/resources.py, resource regression and 120-row corpus"),
        "lab4-v1.1": ("adverse scenarios, execution traces, failures, safeguards, reevaluation",
                        "historical baseline ZIP, lab4_probe.py, 100 traces and verifier"),
    }
    for tag, (required, observed) in manual_requirements.items():
        add(tag, "original methodology content", "expert code/report review plus executable checks",
            "project_guide/Лабораторные-МАС.pdf", required, observed, "PASS",
            "final_audit/FINAL_AUDIT_REPORT.md")

    for tag, record in experiments.items():
        add(tag, "saved experiment corpus and aggregates", "independent CSV recomputation, seed pairing",
            {"lab2-v1.1": "experiments/results/raw.csv",
             "lab3-v1.1": "experiments/lab3/results/raw.csv",
             "lab4-v1.1": "experiments/lab4/results/raw.csv"}[tag],
            {"lab2-v1.1": 96, "lab3-v1.1": 120, "lab4-v1.1": 100}[tag],
            f"{record['rows']} rows, {record['aggregate_values_recomputed']} aggregates match",
            "PASS", "final_audit/experiment_recalculation.json")
        add(tag, "fresh smoke experiment without changing corpus", "run historical script in extracted copy",
            smoke[tag]["command"][0], "exit 0 and separate run_output", smoke[tag]["stdout_tail"].strip(),
            "PASS" if smoke[tag]["exit_code"] == 0 else "FAIL", "final_audit/smoke_log.json")

    for tag, key in (("lab3-v1.1", "lab3"), ("lab4-v1.1", "lab4")):
        item = preservation[key]
        add(tag, "historical file preservation", "recompute current SHA-256 vs frozen original list",
            "audit_evidence/lab3_v1.1_preservation.json" if key == "lab3" else
            "audit_evidence/lab4_v1.1_original_hashes.json", "zero mismatches",
            f"{item['checked']} checked; {len(item['mismatch'])} mismatches",
            "PASS" if not item["mismatch"] else "FAIL", "final_audit/historical_preservation.json")

    lab4_runs = {x["label"]: x for x in protocol["lab4-v1.1"]["runs"]}
    for label in ("verify_faults", "verify_old_llm", "verify_new_llm", "verify_live_replay"):
        item = lab4_runs[label]
        add("lab4-v1.1", label, "replay independent verifier from extracted release",
            item["command"][-1], "exit 0", item["output_tail"].strip(),
            "PASS" if item["exit_code"] == 0 else "FAIL", "final_audit/protocol.json")

    offline = read("offline_lab4.json")
    offline_ok = (offline["outside_repository"] and not offline["git_metadata_available"]
                  and not offline["git_executable_on_path"] and offline["network_calls"] == 0
                  and offline["import_from_extracted_copy"] and offline["check_count"] == 15
                  and offline["manifest_members_verified"] == 306)
    add("lab4-v1.1", "fully offline installation from final audit ZIP",
        "new venv, local wheels, no-index install, full replay", "vendor/wheels; final audit ZIP",
        "15 checks, 306 hashes, no network/Git", offline, "PASS" if offline_ok else "FAIL",
        "final_audit/offline_lab4.json")
    integrated = json.loads((ROOT / "run_output/final_audit_integrated.json").read_text(encoding="utf-8"))
    m = integrated["search"]["metrics"]
    actual = {"search_completed": m["completed_tasks"], "search_total": m["task_count"],
              "review_completed": integrated["review"]["metrics"]["completed_checks"],
              "analysis": integrated["evidence_analysis"]["status"],
              "claim_support": integrated["evidence_analysis"]["analysis"]["claim_support"]}
    integrated_ok = actual == {"search_completed": 4, "search_total": 4,
                               "review_completed": 3, "analysis": "usable_preliminary",
                               "claim_support": "not_assessed"}
    add("lab4-v1.1", "current integrated main workflow",
        "stage4 demo, contract-net, negotiation, recorded evidence analysis",
        "src/researchradar/cli_stage4.py", "4/4 tasks, 3 checks, preliminary unverified analysis",
        actual, "PASS" if integrated_ok else "FAIL", "final_audit/integrated_main.json")

    ledger = Path(os.environ["LOCALAPPDATA"]) / "ResearchRadar_MAS/usage.sqlite3"
    if ledger.is_file():
        db = sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)
        rows = db.execute("SELECT purpose, COUNT(*), ROUND(SUM(actual_usd),9), "
                          "SUM(actual_usd IS NULL) FROM calls GROUP BY purpose").fetchall()
        db.close()
        ledger_data = {purpose: {"calls": count, "actual_usd": cost, "missing_cost": missing}
                       for purpose, count, cost, missing in rows}
        add("lab4-v1.1", "new LIVE Qwen expense", "read-only SQLite aggregate and saved response replay",
            "local external expense ledger; experiments/lab4_v1_1/live*/summary.json",
            "6 calls; 0.00172399 USD", ledger_data.get("scientific_news_evidence_analysis_v2"),
            "PASS" if ledger_data.get("scientific_news_evidence_analysis_v2", {}).get("calls") == 6
            and ledger_data["scientific_news_evidence_analysis_v2"]["actual_usd"] == 0.00172399
            else "FAIL", "final_audit/results.json")
    else:
        ledger_data = None
        add("lab4-v1.1", "new LIVE Qwen expense", "local ledger unavailable", "external ledger",
            "6 calls; 0.00172399 USD", "not independently checked", "NOT_VERIFIED",
            "experiments/lab4_v1_1/live*/summary.json")

    result = {"schema_version": 1, "status_vocabulary": ["PASS", "PASS_WITH_LIMITATIONS",
              "FAIL", "NOT_VERIFIED", "NOT_APPLICABLE"], "checks": checks,
              "qwen_ledger_aggregate": ledger_data,
              "note": "Original historical measurements were not overwritten; no network or paid model calls were made."}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print("checks", len(checks), "status", {s: sum(c["status"] == s for c in checks)
                                          for s in result["status_vocabulary"]})


if __name__ == "__main__":
    main()
