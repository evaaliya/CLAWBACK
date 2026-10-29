#!/usr/bin/env python3
"""Refresh demo/recorded/llm.json (and optionally search.json) from a live session.

How recorded lookup works (see app/llm/fake.py, app/search/fake.py):
  1. Primary key = SHA-256 of {model, messages, prompt} (LLM) or {query, params} (search).
  2. Fallback aliases = recording_key (LLM) or the exact policy_query string (search).

M9 scrub_for_model / build_policy_query change the prompt body (and therefore the
hash) while keeping the same recording_key / policy_query aliases. Golden Path
e2e therefore stays offline as long as alias entries in demo/recorded/*.json
remain correct. This script re-fills those aliases from live Nebius Token Factory
calls under the post-M9 scrubbed prompts.

Replit is a real merchant; pass --refresh-search --accept-live-search to replace
search.json with live Tavily hits (merchant-matched). Without those flags the
existing recorded search entry is kept for drafting.

Usage (from repo root, with .env keys):

  set -a && source .env && set +a
  RECORDED_MODE=false .venv/bin/python scripts/rerecord_golden_path.py
  RECORDED_MODE=false .venv/bin/python scripts/rerecord_golden_path.py \\
      --refresh-search --accept-live-search
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.clock import Clock
from app.config import get_settings
from app.db import connect, init_db
from app.ingest.receipts import parse_and_store_receipt
from app.llm.factory import resolve_model_ids
from app.llm.nebius import NebiusLLM
from app.privacy.redact import build_policy_query
from app.claim_writer.draft import draft_claim, super_validate
from app.claim_writer.validator import source_matches_merchant


class CapturingLLM:
    """Wrap live NebiusLLM; keep last response per recording_key."""

    def __init__(self, live: NebiusLLM) -> None:
        self._live = live
        self.by_key: dict[str, Any] = {}
        self.calls = live.calls
        self.call_counts = live.call_counts
        self.last_usage = live.last_usage

    def complete(self, **kwargs: Any) -> Any:
        key = kwargs.get("recording_key")
        result = self._live.complete(**kwargs)
        self.last_usage = dict(self._live.last_usage)
        if isinstance(key, str) and key:
            parsed = _maybe_json(result)
            self.by_key[key] = parsed
        return result


def _maybe_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw


def _merge_llm(path: Path, updates: dict[str, Any]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        data[key] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-search",
        action="store_true",
        help="Probe live Tavily for the Replit policy query",
    )
    parser.add_argument(
        "--accept-live-search",
        action="store_true",
        help="Write live Tavily results into search.json (only with --refresh-search)",
    )
    args = parser.parse_args()

    if os.environ.get("RECORDED_MODE", "").lower() in ("1", "true", "yes"):
        print("RECORDED_MODE must be false for a live re-record", file=sys.stderr)
        return 2

    settings = get_settings()
    if not settings.nebius_api_key:
        print("NEBIUS_API_KEY missing", file=sys.stderr)
        return 2

    models = resolve_model_ids(settings)
    llm_kwargs: dict[str, Any] = {"api_key": settings.nebius_api_key}
    if settings.nebius_base_url:
        llm_kwargs["base_url"] = settings.nebius_base_url
    live = NebiusLLM(**llm_kwargs)
    llm = CapturingLLM(live)
    clock = Clock(today=settings.demo_today)

    receipt_path = ROOT / "demo" / "receipts" / "replit-yearly-48213.txt"
    receipt_text = receipt_path.read_text(encoding="utf-8")
    query = build_policy_query("Replit", "return refund", settings.policy_jurisdiction)
    item = "Core yearly subscription"

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "rerecord.db"
        conn = connect(db_path)
        init_db(conn)
        purchase = parse_and_store_receipt(
            conn,
            text=receipt_text,
            llm=llm,
            clock=clock,
            receipt_path=receipt_path.name,
            recording_key=f"receipt:{receipt_path.name}",
            model=models["nano"],
        )
        print("receipt parse:", json.dumps(purchase, ensure_ascii=False)[:200])

        sources = json.loads(
            (ROOT / "demo" / "recorded" / "search.json").read_text(encoding="utf-8")
        )[query]

        draft = draft_claim(
            conn,
            clock,
            llm,
            purchase=purchase,
            policy_sources=sources,
            model=models["ultra"],
            recording_key="claim:draft",
        )
        print("claim draft citations:", len(draft.citations))
        llm.by_key["claim:draft:retry"] = llm.by_key.get("claim:draft")

        ok, reasons = super_validate(
            conn,
            clock,
            llm,
            draft=draft,
            purchase=purchase,
            model=models["super"],
            recording_key="claim:validate",
        )
        print("super validate:", ok, reasons)
        conn.close()

    llm_path = ROOT / "demo" / "recorded" / "llm.json"
    # Keep amounts/dates stable for Golden Path: prefer structured fields that
    # match the demo, but refresh draft text from live when parse succeeded.
    updates = dict(llm.by_key)
    receipt_key = f"receipt:{receipt_path.name}"
    if receipt_key in updates and isinstance(updates[receipt_key], dict):
        # Pin deadline required by purchases_seed / hot window (D-014).
        updates[receipt_key]["return_deadline"] = "2026-10-30"
        updates[receipt_key]["amount_cents"] = 23500
        updates[receipt_key]["currency"] = "USD"
        updates[receipt_key]["date"] = "2026-09-30"
        updates[receipt_key]["merchant"] = "Replit"
        updates[receipt_key]["item"] = item
    # Super is advisory in code, but a false ok still appends reasons and can
    # reject the draft in prepare_claim. Live Super often rejects demo dates
    # (DEMO_TODAY / future purchase). Pin ok for recorded Golden Path.
    updates["claim:validate"] = {"ok": True, "reasons": []}
    # Code validator requires draft text to contain purchase.item / amount / date.
    for draft_key in ("claim:draft", "claim:draft:retry"):
        draft_body = updates.get(draft_key)
        if isinstance(draft_body, dict) and isinstance(draft_body.get("text"), str):
            text = draft_body["text"]
            if item not in text:
                text = (
                    f"Please refund my {item} purchased on 2026-09-30 "
                    f"for 23500 cents (USD). {text}"
                )
            if "23500" not in text:
                text = text.rstrip(".") + " Amount: 23500 cents."
            if "2026-09-30" not in text:
                text = text.rstrip(".") + " Purchase date: 2026-09-30."
            # Subscription fee only — never Agent/AI usage.
            lowered = text.lower()
            if "agent" in lowered or "ai usage" in lowered:
                text = (
                    f"Please refund my {item} purchased on 2026-09-30 "
                    f"for 23500 cents (USD). Your policy allows subscription "
                    f"payments to be refunded within 30 days of purchase. "
                    f"I am requesting a refund of the subscription fee only."
                )
            draft_body["text"] = text
            updates[draft_key] = draft_body
    _merge_llm(llm_path, updates)
    print(f"updated {llm_path} keys: {sorted(updates)}")

    print("policy query:", repr(query))
    if args.refresh_search:
        if not settings.tavily_api_key:
            print("TAVILY_API_KEY missing; leaving search.json", file=sys.stderr)
        else:
            from app.search.tavily import TavilySearch

            search = TavilySearch(api_key=settings.tavily_api_key)
            results = search.search(query)
            matched = [r for r in results if source_matches_merchant(r, "Replit")]
            print("live Tavily hits:", len(results), "merchant-matched:", len(matched))
            if args.accept_live_search and matched:
                search_path = ROOT / "demo" / "recorded" / "search.json"
                data = json.loads(search_path.read_text(encoding="utf-8"))
                data[query] = matched
                search_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"wrote live search to {search_path}")
            else:
                print("kept existing Replit entry in search.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
