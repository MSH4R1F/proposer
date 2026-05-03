"""Tests for Phase 9 — labeler runner + run artifact writer."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Type
from unittest.mock import AsyncMock

import pytest

from eval.auto_label.grounder import GroundingDeps
from eval.auto_label.lookups.authorities import InMemoryAuthorityLookup
from eval.auto_label.lookups.statutes import InMemoryStatuteLookup
from eval.auto_label.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_PACK_VERSION,
    prompt_template_hash,
    render_extraction_prompt,
)
from eval.auto_label.runner import (
    RUNNER_VERSION,
    CasePass,
    LabelerOutput,
    LabelingRun,
    run_one_case,
    write_artifact,
)
from llm_orchestrator.clients.base import BaseLLMClient
from llm_orchestrator.clients.labeler_factory import LabelerModelSpec


# ---------------------------------------------------------------------------
# Stub LLM client
# ---------------------------------------------------------------------------


class StubLLMClient(BaseLLMClient):
    """Returns canned JSON responses keyed off the canned dict supplied."""

    def __init__(self, canned: Dict[str, Any]):
        self._canned = canned
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return json.dumps(self._canned)

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[Any],
        max_tokens: int = 4096,
    ) -> Any:  # pragma: no cover - runner uses generate(), not structured
        return response_model.model_validate(self._canned)

    def get_stats(self) -> Dict[str, Any]:
        return {"calls": len(self.calls)}

    def reset_stats(self) -> None:
        self.calls.clear()


# ---------------------------------------------------------------------------
# Prompt template tests
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_hash_is_stable_64_hex(self) -> None:
        h = prompt_template_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
        assert h == prompt_template_hash()

    def test_hash_changes_when_pack_version_does(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = prompt_template_hash()
        import eval.auto_label.prompts.extraction as ext_mod

        monkeypatch.setattr(ext_mod, "PROMPT_PACK_VERSION", "9.9.9")
        assert prompt_template_hash() != original

    def test_render_includes_case_id_and_allowed_fields(self) -> None:
        rendered = render_extraction_prompt(
            case_id="FTT-2023-0001",
            allowed_fields=["facts", "claim_types"],
            pdf_triples=[
                {
                    "page": 1,
                    "paragraph": 1,
                    "section_tag": "pre_decision_record",
                    "char_start": 0,
                    "char_end": 10,
                    "text": "first ten",
                }
            ],
        )
        body = json.loads(rendered)
        assert body["case_id"] == "FTT-2023-0001"
        assert body["allowed_fields"] == sorted({"facts", "claim_types"})
        assert body["prompt_pack_version"] == PROMPT_PACK_VERSION
        assert body["source_text"][0]["section_tag"] == "pre_decision_record"


# ---------------------------------------------------------------------------
# run_one_case
# ---------------------------------------------------------------------------


def _spec(provider: str, model: str) -> LabelerModelSpec:
    return LabelerModelSpec(provider=provider, model=model)


def _make_run(tmp_path: Path) -> LabelingRun:
    return LabelingRun(
        run_id="run-test-001",
        labeler_a_spec=_spec("anthropic", "claude-sonnet-4-20250514"),
        labeler_b_spec=_spec("openai", "gpt-5.5"),
        artifacts_root=tmp_path / "artifacts",
        gold_schema_hash="g" * 16,
        corpus_manifest_hash="c" * 16,
    )


def _make_deps(tmp_path: Path) -> GroundingDeps:
    return GroundingDeps(
        authority_lookup=InMemoryAuthorityLookup(),
        statute_lookup=InMemoryStatuteLookup(),
        run_artifact_path=tmp_path / "missing.json",
    )


class TestRunOneCase:
    def test_dispatches_both_providers_and_returns_partials(
        self, tmp_path: Path
    ) -> None:
        run = _make_run(tmp_path)
        deps = _make_deps(tmp_path)
        canned_a = {"facts": "Tenant moved out 2023-05-31."}
        canned_b = {"facts": "Tenant left at end of May 2023."}
        clients = {
            f"{run.labeler_a_spec.provider}:{run.labeler_a_spec.model}": StubLLMClient(canned_a),
            f"{run.labeler_b_spec.provider}:{run.labeler_b_spec.model}": StubLLMClient(canned_b),
        }

        case_pass = asyncio.run(
            run_one_case(
                case_id="FTT-2023-0001",
                pdf_triples=[
                    {
                        "page": 1,
                        "paragraph": 1,
                        "section_tag": "pre_decision_record",
                        "char_start": 0,
                        "char_end": 10,
                        "text": "first ten",
                    }
                ],
                page_text={1: "first ten"},
                page_sections={(1, 1): "pre_decision_record"},
                source_pdf_sha256="a" * 64,
                ocr_text_sha256="b" * 64,
                run=run,
                clients_by_spec=clients,
                lookups=deps,
            )
        )
        assert isinstance(case_pass, CasePass)
        assert case_pass.labeler_a.partial_case == canned_a
        assert case_pass.labeler_b.partial_case == canned_b
        assert case_pass.labeler_a.spec.provider == "anthropic"
        assert case_pass.labeler_b.spec.provider == "openai"

    def test_provider_independence_two_distinct_clients(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        deps = _make_deps(tmp_path)
        client_a = StubLLMClient({"facts": "A"})
        client_b = StubLLMClient({"facts": "B"})
        clients = {
            f"{run.labeler_a_spec.provider}:{run.labeler_a_spec.model}": client_a,
            f"{run.labeler_b_spec.provider}:{run.labeler_b_spec.model}": client_b,
        }
        asyncio.run(
            run_one_case(
                case_id="C",
                pdf_triples=[],
                page_text={},
                page_sections={},
                source_pdf_sha256="a" * 64,
                ocr_text_sha256="b" * 64,
                run=run,
                clients_by_spec=clients,
                lookups=deps,
            )
        )
        # Each client got exactly one call, proving independence.
        assert client_a is not client_b
        assert len(client_a.calls) == 1
        assert len(client_b.calls) == 1
        # System prompt is the canonical extraction prompt.
        assert client_a.calls[0]["system_prompt"] == EXTRACTION_SYSTEM_PROMPT

    def test_handles_malformed_response(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        deps = _make_deps(tmp_path)
        bad_client = StubLLMClient({})
        # Override generate to return a non-JSON string.
        bad_client.generate = AsyncMock(return_value="not json {{{")  # type: ignore[method-assign]

        clients = {
            f"{run.labeler_a_spec.provider}:{run.labeler_a_spec.model}": bad_client,
            f"{run.labeler_b_spec.provider}:{run.labeler_b_spec.model}": StubLLMClient({}),
        }
        case_pass = asyncio.run(
            run_one_case(
                case_id="C",
                pdf_triples=[],
                page_text={},
                page_sections={},
                source_pdf_sha256="a" * 64,
                ocr_text_sha256="b" * 64,
                run=run,
                clients_by_spec=clients,
                lookups=deps,
            )
        )
        assert case_pass.labeler_a.partial_case == {}


# ---------------------------------------------------------------------------
# write_artifact
# ---------------------------------------------------------------------------


class TestWriteArtifact:
    def test_writes_json_under_run_dir(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        deps = _make_deps(tmp_path)
        clients = {
            f"{run.labeler_a_spec.provider}:{run.labeler_a_spec.model}": StubLLMClient(
                {"facts": "alpha"}
            ),
            f"{run.labeler_b_spec.provider}:{run.labeler_b_spec.model}": StubLLMClient(
                {"facts": "beta"}
            ),
        }
        case_pass = asyncio.run(
            run_one_case(
                case_id="FTT-2023-0001",
                pdf_triples=[],
                page_text={},
                page_sections={},
                source_pdf_sha256="a" * 64,
                ocr_text_sha256="b" * 64,
                run=run,
                clients_by_spec=clients,
                lookups=deps,
            )
        )
        path = write_artifact(case_pass, run=run)
        assert path == run.run_dir / "FTT-2023-0001.json"
        assert path.exists()
        payload = json.loads(path.read_text())
        # Every required reproducibility key is present.
        for key in (
            "case_id",
            "run_id",
            "ran_at",
            "source_pdf_sha256",
            "ocr_text_sha256",
            "prompt_template_hash",
            "prompt_pack_version",
            "canonicalizer_version",
            "grounder_version",
            "runner_version",
            "gold_schema_hash",
            "corpus_manifest_hash",
            "labeler_a",
            "labeler_b",
            "grounding_a",
            "grounding_b",
        ):
            assert key in payload, f"missing {key!r} from artifact"
        assert payload["runner_version"] == RUNNER_VERSION
        assert payload["labeler_a"]["partial_case"] == {"facts": "alpha"}
        assert payload["labeler_b"]["partial_case"] == {"facts": "beta"}
        # Provider independence is replayable from the artifact.
        assert payload["labeler_a"]["spec"]["provider"] != payload["labeler_b"]["spec"]["provider"]

    def test_artifact_path_set_on_case_pass(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        cp = CasePass(
            case_id="x",
            run_id=run.run_id,
            labeler_a=LabelerOutput(
                spec=run.labeler_a_spec,
                rendered_prompt="",
                raw_response="{}",
                partial_case={},
            ),
            labeler_b=LabelerOutput(
                spec=run.labeler_b_spec,
                rendered_prompt="",
                raw_response="{}",
                partial_case={},
            ),
            grounding_a=__import__("eval.auto_label.grounder", fromlist=["GroundingResult"]).GroundingResult(),
            grounding_b=__import__("eval.auto_label.grounder", fromlist=["GroundingResult"]).GroundingResult(),
            source_pdf_sha256="a" * 64,
            ocr_text_sha256="b" * 64,
            prompt_template_hash=prompt_template_hash(),
        )
        assert cp.artifact_path is None
        write_artifact(cp, run=run)
        assert cp.artifact_path is not None
        assert cp.artifact_path.exists()
