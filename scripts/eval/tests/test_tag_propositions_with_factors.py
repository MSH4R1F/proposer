"""Tests for ``scripts.eval.tag_propositions_with_factors``.

Exercises the proposition factor-id tagger CLI end-to-end with a fake
LLM client so no real API calls happen. The point of this module is to
prove:

  * Dry-run validates inputs and renders the sample prompt without an LLM.
  * The tagger merges factor_ids onto the right propositions, in order.
  * Idempotency: re-running on already-tagged input is a no-op (the LLM
    is not called) UNLESS ``--retag`` is passed.
  * Hallucinated factor IDs (not in catalogue) are filtered out.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, List
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages"))

from kg_builder.propositions.models import Proposition  # noqa: E402

from scripts.eval.tag_propositions_with_factors import (  # noqa: E402
    FactorTagBatchResponse,
    FactorTagPrediction,
    PropositionFactorTagger,
    _DEFAULT_GATE_FACTORS_HOUSING_REPAIRS,
    _load_factor_catalogue,
    _resolve_output_path,
    main_async,
    run_tagger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proposition(
    *,
    text: str = "Sample factual claim about a damp report.",
    factor_ids: List[str] | None = None,
    case_reference: str = "case-X",
) -> Proposition:
    return Proposition(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference=case_reference,
        text=text,
        source_passage=text + " (source passage)",
        paragraph_ref="P1",
        proposition_type="fact",
        issue_tags=["housing.repairs_social.v1"],
        entities=[],
        confidence=0.9,
        factor_ids=list(factor_ids or []),
    )


def _write_jsonl(path: Path, propositions: List[Proposition]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for prop in propositions:
            fh.write(prop.model_dump_json() + "\n")


def _read_jsonl(path: Path) -> List[Proposition]:
    out: List[Proposition] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped:
                continue
            out.append(Proposition.model_validate_json(stripped))
    return out


class _FakeLLMClient:
    """Records every call and returns canned responses keyed by call index.

    Matches the duck-typed ``BaseLLMClient.generate_structured`` shape
    consumed by ``PropositionFactorTagger``.
    """

    def __init__(self, scripted_responses: List[FactorTagBatchResponse]) -> None:
        self._responses = list(scripted_responses)
        self.calls: list[dict] = []

    async def generate_structured(
        self,
        *,
        messages: Any,
        system_prompt: str,
        response_model: Any,
        max_tokens: int,
    ) -> Any:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt_chars": len(system_prompt),
                "response_model": response_model,
                "max_tokens": max_tokens,
            }
        )
        if not self._responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Catalogue loading
# ---------------------------------------------------------------------------


def test_load_factor_catalogue_returns_factors():
    factors = _load_factor_catalogue("housing.repairs_social.v1")
    ids = {f.get("id") for f in factors}
    # The 15-factor catalogue must be present
    assert "repair_responsibility_established" in ids
    assert "hazard_or_disrepair_reported" in ids
    assert "landlord_notice_established" in ids


def test_default_gate_factors_subset_of_catalogue():
    catalogue_ids = {
        f.get("id") for f in _load_factor_catalogue("housing.repairs_social.v1")
    }
    for fid in _DEFAULT_GATE_FACTORS_HOUSING_REPAIRS:
        assert fid in catalogue_ids, (
            f"_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS contains unknown id {fid!r}"
        )


def test_load_factor_catalogue_unknown_domain_raises():
    with pytest.raises(ValueError, match="not yet supported"):
        _load_factor_catalogue("housing.deposit.v1")


# ---------------------------------------------------------------------------
# resolve_output_path
# ---------------------------------------------------------------------------


def test_resolve_output_path_default(tmp_path):
    inp = tmp_path / "x.jsonl"
    out = _resolve_output_path(inp, None)
    assert out.name == "x.tagged.jsonl"


def test_resolve_output_path_override(tmp_path):
    inp = tmp_path / "x.jsonl"
    override = tmp_path / "explicit.jsonl"
    assert _resolve_output_path(inp, override) == override


# ---------------------------------------------------------------------------
# Tagger core (unit) — fake LLM client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_batch_indexes_predictions_by_proposition_id():
    p1 = _make_proposition(text="Landlord did not inspect for 100 days.")
    p2 = _make_proposition(text="Repair completed within 5 days of report.")

    response = FactorTagBatchResponse(
        predictions=[
            FactorTagPrediction(
                proposition_id=str(p1.proposition_id),
                factor_ids=["inspection_delay_days"],
                confidence=0.9,
                reasoning="100 days inspection delay",
            ),
            FactorTagPrediction(
                proposition_id=str(p2.proposition_id),
                factor_ids=["repair_attempted"],
                confidence=0.8,
                reasoning="repair completed",
            ),
        ]
    )
    fake = _FakeLLMClient([response])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    out = await tagger.tag_batch([p1, p2])

    assert set(out.keys()) == {str(p1.proposition_id), str(p2.proposition_id)}
    assert out[str(p1.proposition_id)].factor_ids == ["inspection_delay_days"]
    assert out[str(p2.proposition_id)].factor_ids == ["repair_attempted"]
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_tag_batch_filters_hallucinated_factor_ids():
    p1 = _make_proposition(text="Some claim.")
    response = FactorTagBatchResponse(
        predictions=[
            FactorTagPrediction(
                proposition_id=str(p1.proposition_id),
                factor_ids=[
                    "repair_responsibility_established",  # valid
                    "totally_made_up_factor",  # hallucinated
                ],
                confidence=0.7,
                reasoning="...",
            )
        ]
    )
    fake = _FakeLLMClient([response])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    out = await tagger.tag_batch([p1])
    assert out[str(p1.proposition_id)].factor_ids == [
        "repair_responsibility_established"
    ]


@pytest.mark.asyncio
async def test_tag_batch_empty_input_skips_llm():
    fake = _FakeLLMClient([])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    out = await tagger.tag_batch([])
    assert out == {}
    assert fake.calls == []


# ---------------------------------------------------------------------------
# run_tagger — output ordering, factor_ids merge, skip already-tagged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_tagger_preserves_input_order_and_merges_factor_ids():
    p1 = _make_proposition(text="A")
    p2 = _make_proposition(text="B")
    p3 = _make_proposition(text="C")
    response = FactorTagBatchResponse(
        predictions=[
            FactorTagPrediction(
                proposition_id=str(p3.proposition_id),
                factor_ids=["repair_attempted"],
            ),
            FactorTagPrediction(
                proposition_id=str(p1.proposition_id),
                factor_ids=["hazard_or_disrepair_reported"],
            ),
            FactorTagPrediction(
                proposition_id=str(p2.proposition_id),
                factor_ids=[],
            ),
        ]
    )
    fake = _FakeLLMClient([response])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )

    tagged = await run_tagger(
        propositions=[p1, p2, p3],
        tagger=tagger,
        batch_size=10,
        retag=False,
    )
    # Order preserved
    assert [str(t.proposition_id) for t in tagged] == [
        str(p1.proposition_id),
        str(p2.proposition_id),
        str(p3.proposition_id),
    ]
    assert tagged[0].factor_ids == ["hazard_or_disrepair_reported"]
    assert tagged[1].factor_ids == []
    assert tagged[2].factor_ids == ["repair_attempted"]


@pytest.mark.asyncio
async def test_run_tagger_skips_already_tagged_unless_retag():
    p_already = _make_proposition(
        text="Already tagged",
        factor_ids=["repair_responsibility_established"],
    )
    p_new = _make_proposition(text="Not yet tagged")
    response = FactorTagBatchResponse(
        predictions=[
            FactorTagPrediction(
                proposition_id=str(p_new.proposition_id),
                factor_ids=["hazard_or_disrepair_reported"],
            )
        ]
    )
    fake = _FakeLLMClient([response])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    tagged = await run_tagger(
        propositions=[p_already, p_new],
        tagger=tagger,
        batch_size=10,
        retag=False,
    )
    # Already-tagged keeps its factor_ids; LLM only saw the un-tagged one.
    assert tagged[0].factor_ids == ["repair_responsibility_established"]
    assert tagged[1].factor_ids == ["hazard_or_disrepair_reported"]
    # Verify the LLM only saw 1 proposition in its single batch
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_run_tagger_retag_overrides_existing_factor_ids():
    p = _make_proposition(
        text="Retag this one",
        factor_ids=["repair_responsibility_established"],
    )
    response = FactorTagBatchResponse(
        predictions=[
            FactorTagPrediction(
                proposition_id=str(p.proposition_id),
                factor_ids=["vulnerability_known"],
            )
        ]
    )
    fake = _FakeLLMClient([response])
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    tagged = await run_tagger(
        propositions=[p],
        tagger=tagger,
        batch_size=10,
        retag=True,
    )
    assert tagged[0].factor_ids == ["vulnerability_known"]


@pytest.mark.asyncio
async def test_run_tagger_chunks_into_batches():
    """When the input exceeds batch_size, the tagger must issue multiple calls."""
    propositions = [_make_proposition(text=f"prop-{i}") for i in range(7)]
    # Two batches of size 3 + 1 batch of size 1 = 3 LLM calls when batch_size=3
    responses = []
    for batch_idx, start in enumerate(range(0, 7, 3)):
        chunk = propositions[start : start + 3]
        responses.append(
            FactorTagBatchResponse(
                predictions=[
                    FactorTagPrediction(
                        proposition_id=str(p.proposition_id),
                        factor_ids=["repair_attempted"],
                    )
                    for p in chunk
                ]
            )
        )
    fake = _FakeLLMClient(responses)
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    tagged = await run_tagger(
        propositions=propositions,
        tagger=tagger,
        batch_size=3,
        retag=False,
    )
    assert len(tagged) == 7
    assert all(p.factor_ids == ["repair_attempted"] for p in tagged)
    assert len(fake.calls) == 3


# ---------------------------------------------------------------------------
# CLI — dry-run end-to-end (no LLM)
# ---------------------------------------------------------------------------


def test_main_async_dry_run_smoke(tmp_path, capsys):
    p = _make_proposition(text="some claim")
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [p])
    out = tmp_path / "out.jsonl"

    rc = asyncio.run(
        main_async(
            [
                "--input",
                str(inp),
                "--output",
                str(out),
                "--domain",
                "housing.repairs_social.v1",
                "--dry-run",
                "--batch-size",
                "4",
            ]
        )
    )
    assert rc == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["mode"] == "dry-run"
    assert payload["n_propositions"] == 1
    assert payload["batch_size"] == 4
    assert "factor_ids" in payload
    assert payload["sample_user_prompt_chars"] > 0
    # Output file must NOT have been written in dry-run mode
    assert not out.exists()


def test_main_async_errors_on_missing_input(tmp_path, capsys):
    rc = asyncio.run(
        main_async(
            [
                "--input",
                str(tmp_path / "nope.jsonl"),
                "--domain",
                "housing.repairs_social.v1",
                "--dry-run",
            ]
        )
    )
    assert rc == 2
    assert "does not exist" in capsys.readouterr().err


def test_main_async_errors_on_empty_input(tmp_path, capsys):
    inp = tmp_path / "empty.jsonl"
    inp.write_text("", encoding="utf-8")
    rc = asyncio.run(
        main_async(
            [
                "--input",
                str(inp),
                "--domain",
                "housing.repairs_social.v1",
                "--dry-run",
            ]
        )
    )
    assert rc == 2
    assert "no propositions" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Idempotency on disk — running twice produces same output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_tagger_idempotent_when_no_retag(tmp_path):
    """Running the tagger twice on the same already-tagged input must produce
    byte-identical output (when --retag is NOT set).
    """
    catalogue = _load_factor_catalogue("housing.repairs_social.v1")

    p_unset = _make_proposition(text="Untagged claim")
    p_tagged = _make_proposition(
        text="Already tagged",
        factor_ids=["repair_responsibility_established"],
    )

    # First run — fake LLM tags p_unset
    fake = _FakeLLMClient(
        [
            FactorTagBatchResponse(
                predictions=[
                    FactorTagPrediction(
                        proposition_id=str(p_unset.proposition_id),
                        factor_ids=["hazard_or_disrepair_reported"],
                    )
                ]
            )
        ]
    )
    tagger = PropositionFactorTagger(
        fake, catalogue, valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS
    )
    pass1 = await run_tagger(
        propositions=[p_unset, p_tagged],
        tagger=tagger,
        batch_size=10,
        retag=False,
    )
    assert pass1[0].factor_ids == ["hazard_or_disrepair_reported"]
    assert pass1[1].factor_ids == ["repair_responsibility_established"]

    # Second run on the OUTPUT — every prop is already tagged, LLM must
    # NOT be called.
    fake_should_not_run = _FakeLLMClient([])
    tagger2 = PropositionFactorTagger(
        fake_should_not_run,
        catalogue,
        valid_factor_ids=_DEFAULT_GATE_FACTORS_HOUSING_REPAIRS,
    )
    pass2 = await run_tagger(
        propositions=pass1,
        tagger=tagger2,
        batch_size=10,
        retag=False,
    )
    assert fake_should_not_run.calls == [], (
        "second run on already-tagged input must skip the LLM entirely"
    )
    # Byte-stable when serialised
    serialised1 = "\n".join(p.model_dump_json() for p in pass1)
    serialised2 = "\n".join(p.model_dump_json() for p in pass2)
    assert serialised1 == serialised2
