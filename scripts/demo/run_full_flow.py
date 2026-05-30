#!/usr/bin/env python3
"""
Run end-to-end Proposer demo: bulk intake → prediction → join → mediation → settlement.

Usage:
  python scripts/demo/run_full_flow.py --scenario tenant-led
  python scripts/demo/run_full_flow.py --scenario landlord-led
  python scripts/demo/run_full_flow.py --scenario both --json-out docs/demo/last-run.json

Requires API at PROPOSER_API_URL (default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "docs" / "demo" / "example-cases"
DEFAULT_API = "http://localhost:8000"
DOMAIN_ID = "housing.deposit.v1"


def _read_case_text(name: str) -> str:
    path = EXAMPLES_DIR / name
    text = path.read_text(encoding="utf-8")
    marker = "## Case text (copy into Proposer)"
    if marker in text:
        after = text.split(marker, 1)[1].strip()
        next_heading = after.find("\n## ")
        return after[:next_heading].strip() if next_heading >= 0 else after
    return text.strip()


def _request(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: int = 300,
) -> Any:
    url = f"{base.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"{method} {path} failed ({e.code}): {detail}") from e


def bulk_intake(
    base: str,
    *,
    role: str,
    case_text: str,
    create_dispute: bool = True,
    invite_code: str | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "role": role,
        "case_text": case_text,
        "create_dispute": create_dispute,
        "domain_id": DOMAIN_ID,
    }
    if invite_code:
        payload["invite_code"] = invite_code
        payload["create_dispute"] = False
    return _request(base, "POST", "/chat/bulk-intake", payload, timeout=180)


def generate_prediction(base: str, case_id: str) -> dict:
    return _request(
        base,
        "POST",
        "/predictions/generate",
        {"case_id": case_id, "domain_id": DOMAIN_ID},
        timeout=300,
    )


def start_mediation(base: str, dispute_id: str, session_id: str) -> dict:
    return _request(
        base,
        "POST",
        f"/mediation/{dispute_id}/start",
        {"session_id": session_id},
        timeout=120,
    )


def submit_offer(base: str, dispute_id: str, session_id: str, amount: float) -> dict:
    return _request(
        base,
        "POST",
        f"/mediation/{dispute_id}/offer",
        {"session_id": session_id, "amount": amount},
        timeout=60,
    )


def respond_offer(
    base: str,
    dispute_id: str,
    session_id: str,
    offer_id: str,
    action: str,
    counter_amount: float | None = None,
) -> dict:
    body: dict[str, Any] = {
        "session_id": session_id,
        "offer_id": offer_id,
        "action": action,
    }
    if counter_amount is not None:
        body["counter_amount"] = counter_amount
    return _request(base, "POST", f"/mediation/{dispute_id}/respond", body, timeout=120)


def run_scenario(base: str, scenario: str) -> dict:
    """tenant-led: tenant creates dispute; landlord joins. landlord-led: opposite."""
    if scenario == "tenant-led":
        creator_role, joiner_role = "tenant", "landlord"
        creator_case = "tenant-deposit-cleaning-dispute.md"
        joiner_case = "landlord-deposit-damage-dispute.md"
    else:
        creator_role, joiner_role = "landlord", "tenant"
        creator_case = "landlord-deposit-damage-dispute.md"
        joiner_case = "tenant-deposit-cleaning-dispute.md"

    print(f"\n=== {scenario}: {creator_role} creates, {joiner_role} joins ===\n")

    creator = bulk_intake(
        base,
        role=creator_role,
        case_text=_read_case_text(creator_case),
        create_dispute=True,
    )
    creator_session = creator["session_id"]
    creator_case_id = creator["case_file"]["case_id"]
    dispute = creator.get("dispute") or {}
    dispute_id = dispute.get("dispute_id")
    invite_code = dispute.get("invite_code")
    if not dispute_id or not invite_code:
        raise RuntimeError("Creator bulk-intake did not return dispute / invite_code")

    print(f"  Creator session: {creator_session}")
    print(f"  Case ID: {creator_case_id}")
    print(f"  Dispute: {dispute_id}  Invite: {invite_code}")

    print("  Generating prediction (creator case)...")
    t0 = time.time()
    prediction = generate_prediction(base, creator_case_id)
    elapsed = time.time() - t0
    outcome = prediction.get("overall_outcome", prediction.get("predicted_outcome"))
    settlement = prediction.get("predicted_settlement_range")
    print(f"  Prediction in {elapsed:.1f}s — outcome={outcome} range={settlement}")

    print(f"  Joiner ({joiner_role}) bulk-intake with invite...")
    joiner = bulk_intake(
        base,
        role=joiner_role,
        case_text=_read_case_text(joiner_case),
        invite_code=invite_code,
    )
    joiner_session = joiner["session_id"]
    print(f"  Joiner session: {joiner_session}")

    print("  Starting mediation (creator)...")
    start = start_mediation(base, dispute_id, creator_session)
    print(f"  Mediation status: {start.get('status')}")

    # Offer near ZOPA: tenant offers recovery amount; landlord offers retention
    deposit = float(creator["case_file"].get("tenancy", {}).get("deposit_amount") or 1450)
    if creator_role == "tenant":
        offer_amount = round(deposit * 0.65, 0)
        offer_session = creator_session
        accept_session = joiner_session
    else:
        offer_amount = round(deposit * 0.25, 0)
        offer_session = creator_session
        accept_session = joiner_session

    print(f"  Submitting offer £{offer_amount:.0f} from {creator_role}...")
    offer = submit_offer(base, dispute_id, offer_session, offer_amount)
    offer_id = offer.get("offer_id") or offer.get("id")
    if not offer_id:
        raise RuntimeError(f"No offer_id in response: {offer}")

    print(f"  {joiner_role} accepts offer...")
    settled = respond_offer(
        base, dispute_id, accept_session, offer_id, "accept"
    )
    print(f"  Settlement: {settled.get('status', settled)}")

    return {
        "scenario": scenario,
        "dispute_id": dispute_id,
        "invite_code": invite_code,
        "creator": {
            "role": creator_role,
            "session_id": creator_session,
            "case_id": creator_case_id,
        },
        "joiner": {"role": joiner_role, "session_id": joiner_session},
        "prediction": {
            "overall_outcome": outcome,
            "predicted_settlement_range": settlement,
            "prediction_id": prediction.get("prediction_id"),
        },
        "mediation": {
            "offer_amount": offer_amount,
            "settlement_response": settled,
        },
        "urls": {
            "prediction": f"http://localhost:3000/prediction/{creator_case_id}?session={creator_session}&dispute={dispute_id}",
            "mediation_expectation_tenant": f"http://localhost:3000/mediation/{dispute_id}/expectation?session={creator_session if creator_role == 'tenant' else joiner_session}",
            "mediation_expectation_landlord": f"http://localhost:3000/mediation/{dispute_id}/expectation?session={joiner_session if creator_role == 'tenant' else creator_session}",
            "mediation_chat": f"http://localhost:3000/mediation/{dispute_id}/chat?session={creator_session}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Proposer full-flow demo runner")
    parser.add_argument(
        "--scenario",
        choices=("tenant-led", "landlord-led", "both"),
        default="both",
    )
    parser.add_argument("--api-url", default=os.environ.get("PROPOSER_API_URL", DEFAULT_API))
    parser.add_argument(
        "--json-out",
        type=Path,
        default=PROJECT_ROOT / "docs" / "demo" / "last-run.json",
    )
    args = parser.parse_args()
    args.api_url = os.environ.get("PROPOSER_API_URL", args.api_url)

    scenarios = (
        ["tenant-led", "landlord-led"]
        if args.scenario == "both"
        else [args.scenario]
    )
    results = []
    for s in scenarios:
        results.append(run_scenario(args.api_url, s))

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote run manifest: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
