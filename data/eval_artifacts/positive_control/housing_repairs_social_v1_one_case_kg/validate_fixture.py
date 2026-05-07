"""Standalone Pydantic round-trip + cross-reference validator for the
one-case positive-control KG fixture.

Run:

    PYTHONPATH=packages ./venv/bin/python \
        data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/validate_fixture.py

Exits 0 on success, 1 on any validation or cross-reference failure.

Stream C recovery plan Task 7 (data portion).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

from eval.schema import GoldCase
from kg_builder.propositions.models import Proposition
from legal_core.graph.evidence_span import EvidenceSpan
from legal_core.graph.factor_assertion import FactorAssertion
from legal_core.graph.outcome_component import OutcomeComponent

FIXTURE_DIR = Path(__file__).resolve().parent
REPO_ROOT = FIXTURE_DIR.parents[3]
FACTORS_YAML = (
    REPO_ROOT
    / "packages"
    / "domain_packs"
    / "housing"
    / "repairs_social"
    / "factors.yaml"
)
OUTCOMES_YAML = (
    REPO_ROOT
    / "packages"
    / "domain_packs"
    / "housing"
    / "repairs_social"
    / "outcomes.yaml"
)


def _load_json(name: str) -> Any:
    with (FIXTURE_DIR / name).open() as f:
        return json.load(f)


def _load_catalog_factor_ids() -> set:
    with FACTORS_YAML.open() as f:
        catalog = yaml.safe_load(f)
    return {entry["id"] for entry in catalog["factors"]}


def _load_catalog_outcome_ids() -> set:
    with OUTCOMES_YAML.open() as f:
        catalog = yaml.safe_load(f)
    return {entry["id"] for entry in catalog["outcomes"]}


def main() -> int:
    failures: List[str] = []

    # 1. Validate case.json against GoldCase
    case_payload: Dict[str, Any] = _load_json("case.json")
    try:
        gold_case = GoldCase.model_validate(case_payload)
    except Exception as exc:  # noqa: BLE001 — surface every error verbatim
        failures.append(f"case.json: GoldCase validation failed: {exc}")
        gold_case = None

    # 2. Validate evidence_spans.json
    evidence_payload = _load_json("evidence_spans.json")
    evidence_spans: List[EvidenceSpan] = []
    for idx, item in enumerate(evidence_payload):
        try:
            evidence_spans.append(EvidenceSpan.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"evidence_spans.json[{idx}]: validation failed: {exc}"
            )

    # 3. Validate factor_assertions.json
    factor_payload = _load_json("factor_assertions.json")
    factor_assertions: List[FactorAssertion] = []
    for idx, item in enumerate(factor_payload):
        try:
            factor_assertions.append(FactorAssertion.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"factor_assertions.json[{idx}]: validation failed: {exc}"
            )

    # 4. Validate propositions.json
    proposition_payload = _load_json("propositions.json")
    propositions: List[Proposition] = []
    for idx, item in enumerate(proposition_payload):
        try:
            propositions.append(Proposition.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"propositions.json[{idx}]: validation failed: {exc}"
            )

    # 5. Validate outcome_components.json
    outcome_component_payload = _load_json("outcome_components.json")
    outcome_components: List[OutcomeComponent] = []
    for idx, item in enumerate(outcome_component_payload):
        try:
            outcome_components.append(OutcomeComponent.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"outcome_components.json[{idx}]: validation failed: {exc}"
            )

    # 6. Cross-references
    catalog_factor_ids = _load_catalog_factor_ids()
    catalog_outcome_ids = _load_catalog_outcome_ids()

    evidence_span_ids = {es.evidence_span_id for es in evidence_spans}
    factor_ids_in_assertions = {fa.factor_id for fa in factor_assertions}
    proposition_ids = {str(p.proposition_id) for p in propositions}

    # 6a. FactorAssertion catalog membership + supported_by integrity
    for fa in factor_assertions:
        if fa.factor_id not in catalog_factor_ids:
            failures.append(
                f"factor_assertion {fa.factor_assertion_id}: "
                f"factor_id {fa.factor_id!r} is not in factors.yaml"
            )
        for ev_id in fa.supported_by:
            if ev_id not in evidence_span_ids:
                failures.append(
                    f"factor_assertion {fa.factor_assertion_id}: "
                    f"supported_by id {ev_id!r} not in evidence_spans.json"
                )

    # 6b. OutcomeComponent.supporting_factor_ids -> factor_assertions.factor_id
    # OutcomeComponent.supported_by_propositions -> propositions.json ids
    for oc in outcome_components:
        for fid in oc.supporting_factor_ids:
            if fid not in factor_ids_in_assertions:
                failures.append(
                    f"outcome_component {oc.outcome_component_id}: "
                    f"supporting_factor_id {fid!r} not present in "
                    f"factor_assertions.json"
                )
        for fid in oc.mitigating_factor_ids:
            if fid not in catalog_factor_ids:
                failures.append(
                    f"outcome_component {oc.outcome_component_id}: "
                    f"mitigating_factor_id {fid!r} is not in factors.yaml"
                )
        for prop_id in oc.supported_by_propositions:
            if prop_id not in proposition_ids:
                failures.append(
                    f"outcome_component {oc.outcome_component_id}: "
                    f"supported_by_proposition id {prop_id!r} not in "
                    f"propositions.json"
                )

    # 6c. Proposition.factor_ids -> catalog
    for prop in propositions:
        for fid in prop.factor_ids:
            if fid not in catalog_factor_ids:
                failures.append(
                    f"proposition {prop.proposition_id}: factor_id "
                    f"{fid!r} is not in factors.yaml"
                )

    # 7. expected_outcome sanity
    expected_payload: Dict[str, Any] = _load_json("expected_outcome.json")
    if expected_payload.get("determination") not in catalog_outcome_ids:
        failures.append(
            f"expected_outcome.determination "
            f"{expected_payload.get('determination')!r} is not in "
            f"outcomes.yaml"
        )

    # 8. Summary
    print("Positive-control fixture validation summary:")
    print(f"  case.json valid: {gold_case is not None}")
    if gold_case is not None:
        print(f"    case_id: {gold_case.case_id}")
        print(f"    domain_id: {gold_case.domain_id}")
        print(
            f"    determination: "
            f"{gold_case.ground_truth_outcome.determination}"
        )
    print(f"  n_evidence_spans: {len(evidence_spans)}")
    print(f"  n_factor_assertions: {len(factor_assertions)}")
    print(f"  n_propositions: {len(propositions)}")
    print(f"  n_outcome_components: {len(outcome_components)}")

    # Hard non-empty asserts
    for label, count in (
        ("evidence_spans", len(evidence_spans)),
        ("factor_assertions", len(factor_assertions)),
        ("propositions", len(propositions)),
        ("outcome_components", len(outcome_components)),
    ):
        if count <= 0:
            failures.append(f"{label} is empty (must be > 0)")

    if failures:
        print()
        print("FAILURES:")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print()
    print("OK - fixture is valid and self-consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
