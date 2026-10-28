#!/usr/bin/env python3
"""Build reports/verify-<timestamp>.md: T1-T23 status from pytest (JUnit XML) and Playwright (JSON).

A T-item is "closed" when every test named for it ran and passed, "failed" when any named test failed,
and "open" when a named test did not run (missing or skipped).
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

# T-id -> (description, test names that must all pass)
TESTS = {
    "T1": ("Statement yields 4 active subscriptions", ["test_ingest_detects_subscriptions"]),
    "T2": ("Unused threshold boundary", ["test_unused_threshold"]),
    "T3": ("Receipt parsing and needs_review", ["test_receipt_parse_fixture", "test_receipt_bad_json_needs_review"]),
    "T4": ("Money is integer cents", ["test_money_is_integer_cents"]),
    "T5": ("Hot deadline boundary", ["test_deadline_hot_boundary"]),
    "T6": ("Scan is idempotent", ["test_scan_idempotent"]),
    "T7": ("Expired deadline not notified", ["test_expired_not_notified"]),
    "T8": ("No draft without citations", ["test_claim_rejected_without_citations"]),
    "T9": ("Citation must be in Tavily results", ["test_citation_not_in_results_rejected"]),
    "T10": ("Nothing sent without approval", ["test_send_requires_approval"]),
    "T11": ("Approve -> outbox -> refund", ["test_approve_to_outbox_to_refund"]),
    "T12": ("Tavily failure gives no draft", ["test_tavily_failure_no_draft"]),
    "T13": ("Cancel requires confirmation", ["test_cancel_requires_confirmation"]),
    "T14": ("Saved skill, no Ultra call, under 5 s", ["test_skill_reuse_no_ultra"]),
    "T15": ("Ultra path saves a skill", ["test_ultra_path_saves_skill"]),
    "T16": ("Failed replay falls back", ["test_skill_replay_fallback"]),
    "T17": ("Savings plan totals and uniqueness", ["test_savings_plan_totals", "test_savings_event_unique"]),
    "T18": ("Counter equals sum of events after Golden Path", ["test_golden_path_total"]),
    "T19": ("Claim card shows Send, Reject, sources", ["e2e_claim_card"]),
    "T20": ("Recorded mode works offline", ["test_recorded_mode_offline", "e2e_golden_path_offline"]),
    "T21": ("agent_log complete", ["test_agent_log_complete"]),
    "T22": ("Restart keeps state", ["test_restart_keeps_state"]),
    "T23": ("Golden Path three times in a row", ["e2e_golden_path_x3"]),
}


def read_junit(path):
    results = {}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return results
    for case in root.iter("testcase"):
        name = case.get("name", "")
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        results[name] = status
    return results


def read_playwright(path):
    results = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return results

    def walk(suite):
        for spec in suite.get("specs", []):
            ok = spec.get("ok", False)
            skipped = all(
                t.get("status") == "skipped" for t in spec.get("tests", [])
            ) and bool(spec.get("tests"))
            results[spec.get("title", "")] = "skipped" if skipped else ("passed" if ok else "failed")
        for child in suite.get("suites", []):
            walk(child)

    for suite in data.get("suites", []):
        walk(suite)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", required=True)
    ap.add_argument("--playwright", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pytest-rc", type=int, default=0)
    ap.add_argument("--e2e-rc", type=int, default=0)
    args = ap.parse_args()

    results = {}
    results.update(read_junit(args.junit))
    results.update(read_playwright(args.playwright))

    rows, closed, failed, open_ = [], 0, 0, 0
    for tid, (desc, names) in TESTS.items():
        statuses = [results.get(n, "missing") for n in names]
        if any(s == "failed" for s in statuses):
            status = "failed"
            failed += 1
        elif all(s == "passed" for s in statuses):
            status = "closed"
            closed += 1
        else:
            status = "open"
            open_ += 1
        detail = ", ".join(f"`{n}` {s}" for n, s in zip(names, statuses))
        rows.append(f"| {tid} | {status} | {desc} | {detail} |")

    lines = [
        f"# Verify report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"pytest exit code: {args.pytest_rc} · e2e exit code: {args.e2e_rc}",
        "",
        f"Closed: {closed} · Failed: {failed} · Open: {open_} · Total: {len(TESTS)}",
        "",
        "| # | Status | Requirement | Tests |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
    ]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"closed {closed} / failed {failed} / open {open_} of {len(TESTS)}")
    if failed or open_:
        sys.exit(1)


if __name__ == "__main__":
    main()
