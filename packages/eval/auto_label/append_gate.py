"""Real-gold append gate.

Refuses every condition listed in the SHA-28 LLM-labeling sparring document
§8 ("Reporting rules and gates" / "Real-gold append gate"). The gate runs
before a row is appended to ``data/gold_standard/housing_v1.jsonl``: any
violation raises :class:`AppendGateError` naming the failing rule and
offending field/path.

The gate is the deterministic firewall against:

* legacy / hand-annotated rows being mistaken for auto-label-pipeline output
  (``MISSING_LABELING_PROVENANCE``)
* negative-set fixtures being silently appended as real gold
  (``NEGATIVE_KIND_NOT_NONE``)
* leakage controls being missed because the SHA-20 envelope fields are unset
  (``MISSING_TARGET_SOURCE_ID``, ``MISSING_MANIFEST_FIELD``)
* MandatoryReviewSet rows reaching the corpus without a recorded human
  decision (``INCOMPLETE_MANDATORY_REVIEW``)
* the per-case run artifact being missing or hash-mismatched against
  the labeling provenance (``MISSING_RUN_ARTIFACT``,
  ``ARTIFACT_HASH_MISMATCH``).

Only this module knows what "appendable to housing_v1.jsonl" means; callers
(the auto-label CLI, future merge tools) call ``assert_real_gold_appendable``
exactly once per case.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from eval.schema import FieldLabelProvenance, GoldCase


class AppendGateError(ValueError):
    """Raised when a :class:`GoldCase` cannot be appended to housing_v1.jsonl."""


class AppendGateRule(str, Enum):
    MISSING_LABELING_PROVENANCE = "missing_labeling_provenance"
    NEGATIVE_KIND_NOT_NONE = "negative_kind_not_none"
    MISSING_TARGET_SOURCE_ID = "missing_target_source_id"
    MISSING_MANIFEST_FIELD = "missing_manifest_field"
    INCOMPLETE_MANDATORY_REVIEW = "incomplete_mandatory_review"
    MISSING_RUN_ARTIFACT = "missing_run_artifact"
    ARTIFACT_METADATA_MISMATCH = "artifact_metadata_mismatch"
    ARTIFACT_HASH_MISMATCH = "artifact_hash_mismatch"


# Cites sparring §1 ("MandatoryReviewSet for every real gold case"). The
# per-issue paths are added dynamically in ``_expected_mandatory_paths``
# from the case's actual ``ground_truth_outcome.per_issue`` entries (and
# ``unapportioned_reason`` is added when set, replacing per-issue paths).
MANDATORY_REVIEW_FIELDS: frozenset[str] = frozenset(
    {
        "facts",
        "disputed_amount_gbp",
        "claim_types",
        "matter_type",
        "ground_truth_outcome.overall_winner",
        "ground_truth_outcome.total_awarded_gbp",
    }
)

# SHA-20 Phase 7 deterministic-envelope fields that MUST be set on a real
# gold row. Cites sparring §1 / §8. ``target_source_id`` is checked
# separately because it gets its own dedicated rule in §8.
REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "domain_id",
    "forum",
    "retrieval_namespace_id",
    "corpus_version",
    "source_publisher",
    "source_kind",
    "source_license",
)

PROVENANCE_ARTIFACT_FIELDS: tuple[str, ...] = (
    "source_pdf_sha256",
    "ocr_text_sha256",
    "prompt_template_hash",
    "gold_schema_hash",
    "corpus_manifest_hash",
    "canonicalizer_version",
    "grounder_version",
)

# Sources counted as "the human looked at this cell" for MandatoryReviewSet
# coverage. ``deterministic_manifest`` and ``model_agreement`` are NOT
# sufficient because the whole point of the mandatory-review set is that a
# human reviewed the cell regardless of LLM agreement.
_HUMAN_REVIEW_SOURCES: frozenset[str] = frozenset(
    {
        "human_mandatory_review",
        "human_disagreement_adjudication",
        "human_only_anchor",
    }
)


def _raise(rule: AppendGateRule, detail: str) -> None:
    """Raise an ``AppendGateError`` whose message starts with the rule name."""
    raise AppendGateError(f"{rule.value}: {detail}")


def _expected_mandatory_paths(gc: GoldCase) -> set[str]:
    """The set of field paths a real gold case must have human-reviewed.

    Adds per-issue paths for each entry in the case's actual
    ``ground_truth_outcome.per_issue`` list. When the outcome is
    unapportioned (``unapportioned_reason`` set), per-issue paths are
    replaced by a single ``ground_truth_outcome.unapportioned_reason``
    entry — sparring §1 lists ``ground_truth_outcome.unapportioned_reason``
    in MandatoryReviewSet, and ``GroundTruthOutcome._validate_apportionment``
    forbids both being non-empty at once.
    """
    paths: set[str] = set(MANDATORY_REVIEW_FIELDS)
    gto = gc.ground_truth_outcome
    if gto.unapportioned_reason is not None:
        paths.add("ground_truth_outcome.unapportioned_reason")
    else:
        for io in gto.per_issue:
            issue = io.issue
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].winner")
            paths.add(f"ground_truth_outcome.per_issue[issue={issue}].awarded_gbp")
    return paths


def _human_reviewed_paths(field_provenance: list[FieldLabelProvenance]) -> set[str]:
    return {fp.field_path for fp in field_provenance if fp.source in _HUMAN_REVIEW_SOURCES}


def _load_artifact(run_artifact_path: Path) -> dict[str, Any]:
    try:
        return json.loads(run_artifact_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _raise(
            AppendGateRule.MISSING_RUN_ARTIFACT,
            f"could not read run artifact at {run_artifact_path}: {exc}",
        )
        raise  # unreachable; satisfies type checkers


def _missing_manifest_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def assert_real_gold_appendable(
    gc: GoldCase,
    *,
    run_artifact_path: Path,
) -> None:
    """Raise :class:`AppendGateError` if ``gc`` cannot be appended.

    Checks run in the order documented in sparring §8. The first failure
    short-circuits — callers get one rule violation at a time so error
    messages stay specific.
    """
    # Rule 1: labeling provenance must be present.
    if gc.labeling_provenance is None:
        _raise(
            AppendGateRule.MISSING_LABELING_PROVENANCE,
            "GoldCase.labeling_provenance is None; only auto-label-pipeline "
            "rows are appendable to housing_v1.jsonl",
        )
    assert gc.labeling_provenance is not None  # narrow for the rest of the fn

    # Rule 2: negative-set fixtures never go through this gate.
    if gc.negative_kind is not None:
        _raise(
            AppendGateRule.NEGATIVE_KIND_NOT_NONE,
            f"GoldCase.negative_kind={gc.negative_kind!r} — negative-set "
            "fixtures must not be appended as real gold",
        )

    # Rule 3: target_source_id must be set so leakage controls can exclude it.
    if _missing_manifest_value(gc.target_source_id):
        _raise(
            AppendGateRule.MISSING_TARGET_SOURCE_ID,
            "GoldCase.target_source_id is missing or blank; retrieval cannot "
            "exclude the source decision at eval time",
        )

    # Rule 4: every required SHA-20 manifest field must be set.
    for field_name in REQUIRED_MANIFEST_FIELDS:
        if _missing_manifest_value(getattr(gc, field_name)):
            _raise(
                AppendGateRule.MISSING_MANIFEST_FIELD,
                f"GoldCase.{field_name} is missing or blank; deterministic "
                "envelope incomplete",
            )

    # Rule 5: every MandatoryReviewSet path must have a human-reviewed entry
    # in field_provenance.
    expected = _expected_mandatory_paths(gc)
    reviewed = _human_reviewed_paths(gc.labeling_provenance.field_provenance)
    missing = sorted(expected - reviewed)
    if missing:
        _raise(
            AppendGateRule.INCOMPLETE_MANDATORY_REVIEW,
            "MandatoryReviewSet incomplete; missing human review for: "
            + ", ".join(missing),
        )

    # Rule 6: the per-case run artifact file must exist.
    if not run_artifact_path.exists():
        _raise(
            AppendGateRule.MISSING_RUN_ARTIFACT,
            f"run artifact not found at {run_artifact_path}",
        )

    # Rule 7: artifact identity + reproducibility fields must match the row
    # being appended. This prevents a human decisions file for one case/run
    # from being accidentally paired with another case's artifact.
    artifact = _load_artifact(run_artifact_path)
    if artifact.get("case_id") != gc.case_id:
        _raise(
            AppendGateRule.ARTIFACT_METADATA_MISMATCH,
            f"case_id mismatch: artifact={artifact.get('case_id')!r}, "
            f"GoldCase.case_id={gc.case_id!r}",
        )
    if artifact.get("run_id") != gc.labeling_provenance.run_id:
        _raise(
            AppendGateRule.ARTIFACT_METADATA_MISMATCH,
            f"run_id mismatch: artifact={artifact.get('run_id')!r}, "
            f"labeling_provenance.run_id={gc.labeling_provenance.run_id!r}",
        )
    if gc.source_pdf_sha256 != gc.labeling_provenance.source_pdf_sha256:
        _raise(
            AppendGateRule.ARTIFACT_HASH_MISMATCH,
            "source_pdf_sha256 mismatch: "
            f"GoldCase={gc.source_pdf_sha256!r}, "
            f"labeling_provenance={gc.labeling_provenance.source_pdf_sha256!r}",
        )

    for hash_field in PROVENANCE_ARTIFACT_FIELDS:
        artifact_value = artifact.get(hash_field)
        provenance_value = getattr(gc.labeling_provenance, hash_field)
        if artifact_value != provenance_value:
            _raise(
                AppendGateRule.ARTIFACT_HASH_MISMATCH,
                f"{hash_field} mismatch: artifact={artifact_value!r}, "
                f"labeling_provenance={provenance_value!r}",
            )
