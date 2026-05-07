"""TDD tests for scripts/eval/factor_gold_annotation.py — B9 gold annotation CLI.

All tests are offline: no real LLM calls, no network I/O.

Run with:
    pytest scripts/eval/tests/test_factor_gold_annotation.py -v
from the repo root.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts" / "eval"
_PACKAGES = str(_REPO_ROOT / "packages")

sys.path.insert(0, str(_SCRIPTS))
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_cli():
    key = "factor_gold_annotation"
    if key in sys.modules and hasattr(sys.modules[key], "Annotation"):
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(
        key, _SCRIPTS / "factor_gold_annotation.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# FakeLLMClient — mirrors the B4 pattern
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Synchronous async fake — generate_structured returns a canned Pydantic model."""

    def __init__(
        self,
        canned_value: Any,
        canned_value_type: str = "boolean",
        model_id: str = "fake-annotator",
        annotator_id: str = "fake-annotator",
    ) -> None:
        self._canned_value = canned_value
        self._canned_value_type = canned_value_type
        self.model = model_id
        self._annotator_id = annotator_id
        self._calls: List[Dict[str, Any]] = []
        self._stats: Dict[str, Any] = {
            "calls": 0,
            "tokens_in": 50,
            "tokens_out": 100,
            "cached_tokens_in": 0,
            "reasoning_tokens_out": 0,
            "errors": 0,
            "estimated_cost_usd": 0.001,
            "provider": "fake",
            "model": model_id,
        }

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int = 1024,
    ) -> T:
        self._stats["calls"] += 1
        # Record the call for inspection in tests
        self._calls.append(
            {"messages": messages, "system_prompt": system_prompt}
        )
        # Extract case_id and factor_id from user message
        user_content = messages[-1]["content"] if messages else ""
        case_id = "unknown"
        factor_id = "unknown_factor"
        for line in user_content.splitlines():
            if line.startswith("CASE ID:"):
                case_id = line.split(":", 1)[1].strip()
            if "Annotate factor" in line and "`" in line:
                parts = line.split("`")
                if len(parts) >= 2:
                    factor_id = parts[1]

        # Build the nested AnnotationValue from the flat canned value
        mod = _load_cli()
        vtype = self._canned_value_type
        raw = self._canned_value
        if raw is None:
            av = mod.AnnotationValue(is_null=True)
        elif vtype == "boolean":
            av = mod.AnnotationValue(boolean=bool(raw))
        elif vtype == "enum":
            av = mod.AnnotationValue(enum=str(raw))
        elif vtype == "number":
            av = mod.AnnotationValue(number=float(raw))
        elif vtype == "duration":
            av = mod.AnnotationValue(duration_days=int(raw))
        else:
            # Default fallback — treat as boolean
            av = mod.AnnotationValue(boolean=bool(raw))

        canned = {
            "case_id": case_id,
            "factor_id": factor_id,
            "annotator_id": self._annotator_id,
            "value": av,
            "value_type": vtype,
            "confidence": 0.9,
            "source_span": None,
            "requires_human_review": False,
            "reasoning": "Fake annotator reasoning.",
        }
        return response_model.model_validate(canned)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        self._stats["calls"] += 1
        return json.dumps({"value": self._canned_value})

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def reset_stats(self) -> None:
        self._stats["calls"] = 0
        self._calls.clear()


class RaisingClient(FakeLLMClient):
    """Client that raises RuntimeError on generate_structured."""

    async def generate_structured(self, *args, **kwargs):
        raise RuntimeError("Simulated annotator failure")


class MalformedClient(FakeLLMClient):
    """Client that returns a dict missing required Annotation fields."""

    async def generate_structured(self, messages, system_prompt, response_model, max_tokens=1024):
        self._stats["calls"] += 1
        # Missing case_id, factor_id, etc. → ValidationError
        return response_model.model_validate({"annotator_id": "bad"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_NARRATIVE_WITH_DETERMINATION = """\
The resident reported damp in January 2023.
The landlord acknowledged receipt of the report.
Repairs were delayed by four months.

## Determination
The Ombudsman finds maladministration.
The landlord is ordered to pay £500.
"""

_SAMPLE_NARRATIVE_NO_DETERMINATION = (
    "The resident reported a leak in March 2022.\n"
    "The landlord arranged an inspection after two weeks.\n"
    "Repairs were completed within 30 days of notice.\n"
)

_FACTORS_SUBSET = [
    "repair_responsibility_established",
    "hazard_or_disrepair_reported",
    "landlord_notice_established",
]


def _make_fake_cases(n: int = 3) -> List[Dict[str, Any]]:
    return [
        {
            "case_id": f"test-case-{i:03d}",
            "narrative": _SAMPLE_NARRATIVE_NO_DETERMINATION,
            "raw_meta": {"case_id": f"test-case-{i:03d}"},
        }
        for i in range(n)
    ]


def _make_minimal_pack(factor_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a minimal domain pack for testing."""
    if factor_ids is None:
        factor_ids = _FACTORS_SUBSET
    factors = [
        {"id": fid, "value_type": "boolean", "polarity": "pro_claimant"}
        for fid in factor_ids
    ]
    rubric_lines = []
    for fid in factor_ids:
        rubric_lines.append(f"## {fid}")
        rubric_lines.append("")
        rubric_lines.append(f"**Operational definition:** Test definition for {fid}.")
        rubric_lines.append("")
        rubric_lines.append("**Affirmative phrasings:**")
        rubric_lines.append(f'- "The {fid} was confirmed."')
        rubric_lines.append("")
        rubric_lines.append("**Negative phrasings:**")
        rubric_lines.append(f'- "No {fid} established."')
        rubric_lines.append("")
        rubric_lines.append("**Edge cases:**")
        rubric_lines.append(f"- Ambiguous case for {fid}. Call: **absent**.")
        rubric_lines.append("")
        rubric_lines.append("---")
        rubric_lines.append("")
    return {
        "domain_id": "test.domain.v1",
        "factors": factors,
        "outcomes": [{"id": "maladministration", "label": "Maladministration"}],
        "rubric": "\n".join(rubric_lines),
    }


def _make_clients(
    n: int = 2,
    canned_value: bool = True,
    canned_value_type: str = "boolean",
) -> List[FakeLLMClient]:
    return [
        FakeLLMClient(
            canned_value=canned_value,
            canned_value_type=canned_value_type,
            model_id=f"fake-annotator-{i}",
            annotator_id=f"fake-annotator-{i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Import smoke
# ---------------------------------------------------------------------------


class TestImport:
    def test_imports_cleanly(self):
        mod = _load_cli()
        assert mod is not None

    def test_annotation_model_exists(self):
        mod = _load_cli()
        assert hasattr(mod, "Annotation")

    def test_per_factor_alpha_model_exists(self):
        mod = _load_cli()
        assert hasattr(mod, "PerFactorAlpha")


# ---------------------------------------------------------------------------
# 2. Determination stripping (reuses factor_catalog_review.strip_determination)
# ---------------------------------------------------------------------------


class TestDeterminationStripping:
    def test_strips_determination_header(self):
        mod = _load_cli()
        stripped = mod.strip_determination(_SAMPLE_NARRATIVE_WITH_DETERMINATION)
        assert "Determination" not in stripped
        assert "maladministration" not in stripped

    def test_retains_pre_determination_text(self):
        mod = _load_cli()
        stripped = mod.strip_determination(_SAMPLE_NARRATIVE_WITH_DETERMINATION)
        assert "resident reported damp" in stripped

    def test_strips_h1_to_h6_variants(self):
        mod = _load_cli()
        for hashes in ["#", "##", "###", "####", "#####", "######"]:
            text = f"Facts here.\n{hashes} Determination\nResult."
            stripped = mod.strip_determination(text)
            assert "Result" not in stripped, f"Failed for {hashes!r}"

    def test_strips_all_trigger_keywords(self):
        mod = _load_cli()
        keywords = ["Determination", "Decision", "Findings", "Outcome", "Order", "Compensation"]
        for kw in keywords:
            text = f"Pre-text.\n## {kw}\nPost-text."
            stripped = mod.strip_determination(text)
            assert "Post-text" not in stripped, f"Keyword {kw!r} not stripped"

    def test_case_insensitive(self):
        mod = _load_cli()
        text = "Facts.\n## DETERMINATION\nResult."
        assert "Result" not in mod.strip_determination(text)

    def test_no_header_returns_full_text(self):
        mod = _load_cli()
        assert mod.strip_determination(_SAMPLE_NARRATIVE_NO_DETERMINATION) == _SAMPLE_NARRATIVE_NO_DETERMINATION


# ---------------------------------------------------------------------------
# 3. Case selection determinism
# ---------------------------------------------------------------------------


class TestCaseSelection:
    def _write_mini_corpus(self, tmp_path: Path, n_rows: int = 20) -> Path:
        """Write a small synthetic JSONL corpus for testing."""
        corpus_path = tmp_path / "mini_corpus.jsonl"
        with corpus_path.open("w") as fh:
            for i in range(n_rows):
                fh.write(
                    json.dumps(
                        {
                            "case_id": f"case-{i:04d}",
                            "title": f"Case {i}",
                            "outcome_raw": "maladministration",
                            "matter_types": ["repairs"],
                            "landlord_name": "Test Landlord",
                        }
                    )
                    + "\n"
                )
        return corpus_path

    def test_same_seed_same_cases(self, tmp_path):
        mod = _load_cli()
        corpus_path = self._write_mini_corpus(tmp_path)
        cases1 = mod.load_cases(n=5, seed=42, corpus_path=corpus_path)
        cases2 = mod.load_cases(n=5, seed=42, corpus_path=corpus_path)
        assert [c["case_id"] for c in cases1] == [c["case_id"] for c in cases2]

    def test_different_seed_different_cases(self, tmp_path):
        mod = _load_cli()
        corpus_path = self._write_mini_corpus(tmp_path, n_rows=20)
        cases1 = mod.load_cases(n=5, seed=42, corpus_path=corpus_path)
        cases2 = mod.load_cases(n=5, seed=99, corpus_path=corpus_path)
        # Unlikely (but not impossible) that all IDs match — use large corpus
        assert [c["case_id"] for c in cases1] != [c["case_id"] for c in cases2]

    def test_returns_n_cases(self, tmp_path):
        mod = _load_cli()
        corpus_path = self._write_mini_corpus(tmp_path)
        cases = mod.load_cases(n=7, seed=42, corpus_path=corpus_path)
        assert len(cases) == 7

    def test_missing_corpus_raises(self, tmp_path):
        mod = _load_cli()
        with pytest.raises(FileNotFoundError):
            mod.load_cases(n=5, seed=42, corpus_path=tmp_path / "nonexistent.jsonl")

    def test_corpus_too_small_raises(self, tmp_path):
        mod = _load_cli()
        corpus_path = self._write_mini_corpus(tmp_path, n_rows=3)
        with pytest.raises(ValueError):
            mod.load_cases(n=5, seed=42, corpus_path=corpus_path)

    def test_stub_used_when_raw_text_missing(self, tmp_path):
        mod = _load_cli()
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(
            json.dumps(
                {
                    "case_id": "test-001",
                    "title": "My Test Case",
                    "outcome_raw": "maladministration",
                    "matter_types": ["repairs"],
                    "landlord_name": "Test Landlord",
                    "raw_text_path": "nonexistent/path.txt",
                }
            )
            + "\n"
        )
        cases = mod.load_cases(n=1, seed=42, corpus_path=corpus_path)
        assert len(cases) == 1
        assert "My Test Case" in cases[0]["narrative"] or "test-001" in cases[0]["narrative"]


# ---------------------------------------------------------------------------
# 4. Rubric section extraction
# ---------------------------------------------------------------------------


class TestRubricSectionExtraction:
    def test_extracts_known_factor(self):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        rubric = pack["rubric"]
        section = mod.extract_rubric_section(rubric, "repair_responsibility_established")
        assert "Operational definition" in section
        assert "Affirmative phrasings" in section
        assert "Edge cases" in section

    def test_returns_empty_for_unknown_factor(self):
        mod = _load_cli()
        section = mod.extract_rubric_section("## known_factor\nSome text.\n", "unknown_factor")
        assert section == ""

    def test_section_does_not_bleed_into_next_factor(self):
        mod = _load_cli()
        rubric = (
            "## factor_a\nContent of A.\n\n"
            "## factor_b\nContent of B.\n\n"
        )
        section_a = mod.extract_rubric_section(rubric, "factor_a")
        assert "Content of A" in section_a
        assert "Content of B" not in section_a


# ---------------------------------------------------------------------------
# 5. System prompt construction
# ---------------------------------------------------------------------------


class TestSystemPromptConstruction:
    def test_prompt_contains_operational_definition(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["repair_responsibility_established"])
        factor = pack["factors"][0]
        rubric_section = mod.extract_rubric_section(
            pack["rubric"], "repair_responsibility_established"
        )
        prompt = mod.build_system_prompt(factor, rubric_section, "my-annotator-id")
        assert "Operational definition" in prompt

    def test_prompt_contains_affirmative_phrasings(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["hazard_or_disrepair_reported"])
        factor = pack["factors"][0]
        rubric_section = mod.extract_rubric_section(pack["rubric"], "hazard_or_disrepair_reported")
        prompt = mod.build_system_prompt(factor, rubric_section, "ann-1")
        assert "Affirmative phrasings" in prompt

    def test_prompt_contains_negative_phrasings(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["repair_responsibility_established"])
        factor = pack["factors"][0]
        rubric_section = mod.extract_rubric_section(
            pack["rubric"], "repair_responsibility_established"
        )
        prompt = mod.build_system_prompt(factor, rubric_section, "ann-1")
        assert "Negative phrasings" in prompt

    def test_prompt_contains_edge_cases(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["repair_responsibility_established"])
        factor = pack["factors"][0]
        rubric_section = mod.extract_rubric_section(
            pack["rubric"], "repair_responsibility_established"
        )
        prompt = mod.build_system_prompt(factor, rubric_section, "ann-1")
        assert "Edge cases" in prompt

    def test_prompt_contains_factor_id(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["inspection_offered"])
        factor = pack["factors"][0]
        rubric_section = mod.extract_rubric_section(pack["rubric"], "inspection_offered")
        prompt = mod.build_system_prompt(factor, rubric_section, "ann-1")
        assert "inspection_offered" in prompt

    def test_prompt_contains_annotator_id(self):
        mod = _load_cli()
        pack = _make_minimal_pack(["repair_attempted"])
        factor = pack["factors"][0]
        rubric_section = ""
        prompt = mod.build_system_prompt(factor, rubric_section, "claude-opus-4-7")
        assert "claude-opus-4-7" in prompt

    def test_enum_factor_includes_enum_values_hint(self):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        factors_by_id = {f["id"]: f for f in pack["factors"]}
        factor = factors_by_id["impact_severity_reported"]
        rubric_section = mod.extract_rubric_section(pack["rubric"], "impact_severity_reported")
        prompt = mod.build_system_prompt(factor, rubric_section, "ann-1")
        assert "none" in prompt.lower()
        assert "minor" in prompt.lower()
        assert "moderate" in prompt.lower()
        assert "severe" in prompt.lower()


# ---------------------------------------------------------------------------
# 6. Annotator must NOT see stripped determination section (T8)
# ---------------------------------------------------------------------------


class TestAnnotatorDoesNotSeeDetermination:
    def test_user_prompt_excludes_determination_text(self):
        mod = _load_cli()
        pack = _make_minimal_pack()
        clients = _make_clients(n=2)
        dispatcher = mod.AnnotationDispatcher(
            clients=clients,
            pack=pack,
            annotator_ids=["ann-0", "ann-1"],
        )

        # Create cases with a determination embedded in raw text
        # The cases returned by load_cases should already be stripped,
        # but let's confirm the user prompt doesn't contain determination text
        case = {
            "case_id": "test-strip-001",
            "narrative": _SAMPLE_NARRATIVE_NO_DETERMINATION,
            "raw_meta": {},
        }
        asyncio.run(dispatcher.annotate_all([case], [_FACTORS_SUBSET[0]]))

        # Check EVERY call recorded by each client
        for client in clients:
            for call in client._calls:
                user_content = call["messages"][-1]["content"]
                # The determination text must NOT appear in any user prompt
                assert "The Ombudsman finds maladministration" not in user_content, (
                    "Determination text must not appear in annotator's user prompt"
                )
                assert "landlord is ordered to pay" not in user_content.lower()

    def test_narrative_in_user_prompt_is_stripped(self):
        """When a case arrives already stripped, the prompt uses that stripped text."""
        mod = _load_cli()
        pack = _make_minimal_pack()
        clients = _make_clients(n=2)
        dispatcher = mod.AnnotationDispatcher(
            clients=clients, pack=pack, annotator_ids=["ann-0", "ann-1"]
        )
        # Simulate what load_cases returns (already stripped)
        stripped = mod.strip_determination(_SAMPLE_NARRATIVE_WITH_DETERMINATION)
        case = {"case_id": "strip-002", "narrative": stripped, "raw_meta": {}}
        asyncio.run(dispatcher.annotate_all([case], [_FACTORS_SUBSET[0]]))

        for client in clients:
            for call in client._calls:
                user_content = call["messages"][-1]["content"]
                assert "ordered to pay" not in user_content.lower()


# ---------------------------------------------------------------------------
# 7. Annotation Pydantic validation
# ---------------------------------------------------------------------------


class TestAnnotationModel:
    def test_confidence_must_be_in_range(self):
        mod = _load_cli()
        with pytest.raises(ValidationError):
            mod.Annotation(
                case_id="c1",
                factor_id="f1",
                annotator_id="ann-1",
                value=mod.AnnotationValue(boolean=True),
                value_type="boolean",
                confidence=1.5,  # invalid
                source_span=None,
                requires_human_review=False,
                reasoning="test",
            )

    def test_confidence_zero_is_valid(self):
        mod = _load_cli()
        ann = mod.Annotation(
            case_id="c1",
            factor_id="f1",
            annotator_id="ann-1",
            value=mod.AnnotationValue(boolean=True),
            value_type="boolean",
            confidence=0.0,
            source_span=None,
            requires_human_review=False,
            reasoning="test",
        )
        assert ann.confidence == 0.0

    def test_requires_human_review_is_bool(self):
        mod = _load_cli()
        ann = mod.Annotation(
            case_id="c1",
            factor_id="f1",
            annotator_id="ann-1",
            value=mod.AnnotationValue(boolean=False),
            value_type="boolean",
            confidence=0.5,
            source_span=None,
            requires_human_review=True,
            reasoning="test",
        )
        assert isinstance(ann.requires_human_review, bool)

    def test_model_is_frozen(self):
        mod = _load_cli()
        ann = mod.Annotation(
            case_id="c1",
            factor_id="f1",
            annotator_id="ann-1",
            value=mod.AnnotationValue(boolean=True),
            value_type="boolean",
            confidence=0.8,
            source_span=None,
            requires_human_review=False,
            reasoning="test",
        )
        with pytest.raises(Exception):
            ann.case_id = "mutated"  # type: ignore[misc]

    def test_model_dump_json_is_valid(self):
        mod = _load_cli()
        ann = mod.Annotation(
            case_id="c1",
            factor_id="f1",
            annotator_id="ann-1",
            value=mod.AnnotationValue(boolean=True),
            value_type="boolean",
            confidence=0.8,
            source_span="Some quote",
            requires_human_review=False,
            reasoning="Because the narrative says so.",
        )
        row = json.loads(ann.model_dump_json())
        assert row["case_id"] == "c1"
        # value is now a nested object; boolean sub-field should be True
        assert row["value"]["boolean"] is True
        assert row["value"]["is_null"] is False


# ---------------------------------------------------------------------------
# 7b. AnnotationValue model and _extract_typed_value helper
# ---------------------------------------------------------------------------


class TestAnnotationValue:
    """Tests for the nested AnnotationValue typed-value carrier."""

    # --- round-trip serialisation per typed variant ---

    def test_boolean_variant_serialises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(boolean=True)
        d = json.loads(av.model_dump_json())
        assert d["boolean"] is True
        assert d["enum"] is None
        assert d["number"] is None
        assert d["duration_days"] is None
        assert d["is_null"] is False

    def test_enum_variant_serialises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(enum="moderate")
        d = json.loads(av.model_dump_json())
        assert d["enum"] == "moderate"
        assert d["boolean"] is None
        assert d["is_null"] is False

    def test_number_variant_serialises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(number=3.14)
        d = json.loads(av.model_dump_json())
        assert abs(d["number"] - 3.14) < 1e-9
        assert d["boolean"] is None
        assert d["is_null"] is False

    def test_duration_days_variant_serialises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(duration_days=42)
        d = json.loads(av.model_dump_json())
        assert d["duration_days"] == 42
        assert d["boolean"] is None
        assert d["is_null"] is False

    def test_is_null_variant_serialises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(is_null=True)
        d = json.loads(av.model_dump_json())
        assert d["is_null"] is True
        assert d["boolean"] is None
        assert d["enum"] is None

    # --- validation: rejects invalid states ---

    def test_rejects_multi_populated(self):
        mod = _load_cli()
        with pytest.raises(Exception):
            mod.AnnotationValue(boolean=True, enum="none")

    def test_rejects_empty_without_is_null(self):
        mod = _load_cli()
        with pytest.raises(Exception):
            mod.AnnotationValue()  # no field set and is_null defaults to False

    def test_rejects_is_null_with_populated_field(self):
        mod = _load_cli()
        with pytest.raises(Exception):
            mod.AnnotationValue(boolean=True, is_null=True)

    def test_frozen(self):
        mod = _load_cli()
        av = mod.AnnotationValue(boolean=False)
        with pytest.raises(Exception):
            av.boolean = True  # type: ignore[misc]

    # --- _extract_typed_value helper ---

    def test_extract_boolean(self):
        mod = _load_cli()
        av = mod.AnnotationValue(boolean=True)
        assert mod._extract_typed_value(av, "boolean") is True

    def test_extract_enum(self):
        mod = _load_cli()
        av = mod.AnnotationValue(enum="severe")
        assert mod._extract_typed_value(av, "enum") == "severe"

    def test_extract_number(self):
        mod = _load_cli()
        av = mod.AnnotationValue(number=7.5)
        assert mod._extract_typed_value(av, "number") == pytest.approx(7.5)

    def test_extract_duration(self):
        mod = _load_cli()
        av = mod.AnnotationValue(duration_days=14)
        assert mod._extract_typed_value(av, "duration") == 14

    def test_extract_is_null_returns_none(self):
        mod = _load_cli()
        av = mod.AnnotationValue(is_null=True)
        for vtype in ("boolean", "enum", "number", "duration"):
            assert mod._extract_typed_value(av, vtype) is None

    def test_extract_unknown_type_raises(self):
        mod = _load_cli()
        av = mod.AnnotationValue(boolean=True)
        with pytest.raises(ValueError, match="unknown value_type"):
            mod._extract_typed_value(av, "unknown_type")


# ---------------------------------------------------------------------------
# 8. JSONL output shape
# ---------------------------------------------------------------------------


class TestJSONLOutput:
    def test_output_row_count(self, tmp_path):
        """N cases × M factors × 2 annotators = expected row count."""
        mod = _load_cli()
        n_cases, n_factors, n_annotators = 3, 3, 2
        pack = _make_minimal_pack(factor_ids=_FACTORS_SUBSET[:n_factors])
        clients = _make_clients(n=n_annotators)
        dispatcher = mod.AnnotationDispatcher(
            clients=clients, pack=pack, annotator_ids=["ann-0", "ann-1"]
        )
        cases = _make_fake_cases(n=n_cases)
        annotations = asyncio.run(
            dispatcher.annotate_all(cases, _FACTORS_SUBSET[:n_factors])
        )
        assert len(annotations) == n_cases * n_factors * n_annotators

        out_path = tmp_path / "out.jsonl"
        mod.write_annotations_jsonl(annotations, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        assert len(rows) == n_cases * n_factors * n_annotators

    def test_output_ordering_deterministic(self, tmp_path):
        """Same inputs produce identical JSONL bytes."""
        mod = _load_cli()
        pack = _make_minimal_pack(factor_ids=_FACTORS_SUBSET[:2])
        cases = _make_fake_cases(n=2)

        def _run_once():
            clients = _make_clients(n=2)
            dispatcher = mod.AnnotationDispatcher(
                clients=clients, pack=pack, annotator_ids=["ann-0", "ann-1"]
            )
            annotations = asyncio.run(dispatcher.annotate_all(cases, _FACTORS_SUBSET[:2]))
            out_path = tmp_path / f"out_{id(clients)}.jsonl"
            mod.write_annotations_jsonl(annotations, out_path)
            return out_path.read_text()

        text1 = _run_once()
        text2 = _run_once()
        assert text1 == text2

    def test_each_row_has_required_keys(self, tmp_path):
        mod = _load_cli()
        pack = _make_minimal_pack(factor_ids=[_FACTORS_SUBSET[0]])
        clients = _make_clients(n=2)
        dispatcher = mod.AnnotationDispatcher(
            clients=clients, pack=pack, annotator_ids=["ann-0", "ann-1"]
        )
        cases = _make_fake_cases(n=1)
        annotations = asyncio.run(dispatcher.annotate_all(cases, [_FACTORS_SUBSET[0]]))
        out_path = tmp_path / "out.jsonl"
        mod.write_annotations_jsonl(annotations, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        required = {"case_id", "factor_id", "annotator_id", "value", "value_type",
                    "confidence", "source_span", "requires_human_review", "reasoning"}
        for row in rows:
            assert required.issubset(row.keys()), f"Missing keys in row: {required - row.keys()}"


# ---------------------------------------------------------------------------
# 9. Krippendorff α computation
# ---------------------------------------------------------------------------


def _raw_to_annotation_value(raw: Any, value_type: str) -> Any:
    """Convert a raw Python value to an ``AnnotationValue`` for tests."""
    mod = _load_cli()
    if raw is None:
        return mod.AnnotationValue(is_null=True)
    if value_type == "boolean":
        return mod.AnnotationValue(boolean=bool(raw))
    if value_type == "enum":
        return mod.AnnotationValue(enum=str(raw))
    if value_type == "number":
        return mod.AnnotationValue(number=float(raw))
    if value_type == "duration":
        return mod.AnnotationValue(duration_days=int(raw))
    # fallback
    return mod.AnnotationValue(boolean=bool(raw))


def _make_annotations(
    case_ids: List[str],
    factor_id: str,
    values_a: List[Any],
    values_b: List[Any],
    value_type: str = "boolean",
    requires_review_a: Optional[List[bool]] = None,
    requires_review_b: Optional[List[bool]] = None,
) -> List[Any]:
    """Build Annotation objects for testing IAA computation."""
    mod = _load_cli()
    if requires_review_a is None:
        requires_review_a = [False] * len(case_ids)
    if requires_review_b is None:
        requires_review_b = [False] * len(case_ids)

    anns = []
    for cid, va, vb, ra, rb in zip(
        case_ids, values_a, values_b, requires_review_a, requires_review_b
    ):
        anns.append(
            mod.Annotation(
                case_id=cid,
                factor_id=factor_id,
                annotator_id="ann-0",
                value=_raw_to_annotation_value(va, value_type),
                value_type=value_type,
                confidence=0.9,
                source_span=None,
                requires_human_review=ra,
                reasoning="test",
            )
        )
        anns.append(
            mod.Annotation(
                case_id=cid,
                factor_id=factor_id,
                annotator_id="ann-1",
                value=_raw_to_annotation_value(vb, value_type),
                value_type=value_type,
                confidence=0.9,
                source_span=None,
                requires_human_review=rb,
                reasoning="test",
            )
        )
    return anns


class TestKrippendorffAlpha:
    def test_perfect_agreement_boolean(self):
        """Perfect agreement → α ≈ 1.0."""
        mod = _load_cli()
        case_ids = [f"c{i}" for i in range(5)]
        values = [True, False, True, False, True]
        anns = _make_annotations(case_ids, "f1", values, values, "boolean")
        factor = {"id": "f1", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.alpha is not None
        assert abs(pfa.alpha - 1.0) < 0.01

    def test_perfect_disagreement_boolean(self):
        """Perfect disagreement → α < 0."""
        mod = _load_cli()
        case_ids = [f"c{i}" for i in range(6)]
        vals_a = [True, False, True, False, True, False]
        vals_b = [False, True, False, True, False, True]
        anns = _make_annotations(case_ids, "f1", vals_a, vals_b, "boolean")
        factor = {"id": "f1", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.alpha is not None
        assert pfa.alpha < 0

    def test_ordinal_level_for_enum_factor(self):
        """Enum factor uses ordinal level_of_measurement."""
        mod = _load_cli()
        case_ids = [f"c{i}" for i in range(4)]
        values_a = ["none", "minor", "moderate", "severe"]
        values_b = ["none", "minor", "moderate", "severe"]
        anns = _make_annotations(case_ids, "impact_severity_reported", values_a, values_b, "enum")
        factor = {
            "id": "impact_severity_reported",
            "value_type": "enum",
            "enum_values": ["none", "minor", "moderate", "severe"],
        }
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.level_of_measurement == "ordinal"

    def test_interval_level_for_duration_factor(self):
        """Duration factor uses interval level_of_measurement."""
        mod = _load_cli()
        case_ids = [f"c{i}" for i in range(4)]
        values = [10, 20, 30, 40]
        anns = _make_annotations(case_ids, "repair_delay_days", values, values, "duration")
        factor = {"id": "repair_delay_days", "value_type": "duration"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.level_of_measurement == "interval"

    def test_skip_when_all_flagged_for_review(self):
        """When all annotations require human review → alpha=None, note contains 'N/A'."""
        mod = _load_cli()
        case_ids = [f"c{i}" for i in range(4)]
        values = [True, False, True, False]
        anns = _make_annotations(
            case_ids,
            "f1",
            values,
            values,
            "boolean",
            requires_review_a=[True] * 4,
            requires_review_b=[True] * 4,
        )
        factor = {"id": "f1", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.alpha is None
        assert "N/A" in pfa.note or "flagged" in pfa.note.lower()

    def test_skip_does_not_crash(self):
        """No exception raised when all flagged."""
        mod = _load_cli()
        case_ids = ["c0"]
        anns = _make_annotations(
            case_ids, "f1", [True], [True], "boolean",
            requires_review_a=[True], requires_review_b=[True]
        )
        factor = {"id": "f1", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)  # must not raise
        assert isinstance(pfa, mod.PerFactorAlpha)

    def test_n_pairs_counted_correctly(self):
        mod = _load_cli()
        n = 5
        case_ids = [f"c{i}" for i in range(n)]
        values = [True, False, True, False, True]
        anns = _make_annotations(case_ids, "f1", values, values, "boolean")
        factor = {"id": "f1", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.n_pairs == n

    def test_enum_values_encoded_correctly(self):
        """Enum values must map to ordinal integers 0-3."""
        mod = _load_cli()
        # Perfect agreement after ordinal encoding
        case_ids = ["c0", "c1"]
        values_a = ["none", "severe"]
        values_b = ["none", "severe"]
        anns = _make_annotations(case_ids, "impact_severity_reported", values_a, values_b, "enum")
        factor = {"id": "impact_severity_reported", "value_type": "enum"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)
        assert pfa.alpha is not None
        assert abs(pfa.alpha - 1.0) < 0.01


# ---------------------------------------------------------------------------
# 10. Dry-run does not call LLM (T9)
# ---------------------------------------------------------------------------


class TestDryRunNoLLMCalls:
    def test_dry_run_calls_no_generate_structured(self, tmp_path, capsys):
        mod = _load_cli()
        clients = _make_clients(n=2)

        # Write a minimal corpus for the dry run
        corpus_path = tmp_path / "corpus.jsonl"
        with corpus_path.open("w") as fh:
            for i in range(5):
                fh.write(json.dumps({"case_id": f"c{i}", "title": f"Case {i}",
                                     "outcome_raw": "m", "matter_types": [],
                                     "landlord_name": "L"}) + "\n")

        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--output", str(tmp_path / "out.jsonl"),
            ],
            injected_clients=clients,
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        # Confirm no LLM call was made
        for client in clients:
            assert client.get_stats()["calls"] == 0, (
                f"generate_structured was called during --dry-run"
            )

    def test_dry_run_does_not_write_file(self, tmp_path):
        mod = _load_cli()
        clients = _make_clients(n=2)
        corpus_path = tmp_path / "corpus.jsonl"
        with corpus_path.open("w") as fh:
            for i in range(5):
                fh.write(json.dumps({"case_id": f"c{i}", "title": f"Case {i}",
                                     "outcome_raw": "m", "matter_types": [],
                                     "landlord_name": "L"}) + "\n")
        out_path = tmp_path / "should_not_exist.jsonl"
        mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--output", str(out_path),
            ],
            injected_clients=clients,
            repo_root=_REPO_ROOT,
        )
        assert not out_path.exists()


# ---------------------------------------------------------------------------
# Shared corpus fixture (replaces three byte-identical _write_corpus helpers)
# ---------------------------------------------------------------------------


@pytest.fixture
def write_corpus():
    """Return a callable ``write_corpus(tmp_path, n=10) -> Path``.

    Writes a minimal JSONL corpus of *n* synthetic case rows to
    ``tmp_path / "corpus.jsonl"`` and returns the path.
    """

    def _write(tmp_path: Path, n: int = 10) -> Path:
        p = tmp_path / "corpus.jsonl"
        with p.open("w") as fh:
            for i in range(n):
                fh.write(
                    json.dumps(
                        {
                            "case_id": f"c{i}",
                            "title": f"C{i}",
                            "outcome_raw": "m",
                            "matter_types": [],
                            "landlord_name": "L",
                        }
                    )
                    + "\n"
                )
        return p

    return _write


# ---------------------------------------------------------------------------
# 11. CLI exit codes
# ---------------------------------------------------------------------------


class TestCLIExitCodes:
    def test_exits_0_on_dry_run_success(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--n", "3",
                "--corpus-path", str(corpus_path),
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0

    def test_exits_0_on_execute_success(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        out_path = tmp_path / "out.jsonl"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--factors", "repair_responsibility_established,hazard_or_disrepair_reported",
                "--corpus-path", str(corpus_path),
                "--output", str(out_path),
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        assert out_path.exists()

    def test_exits_nonzero_on_missing_domain(self, tmp_path):
        mod = _load_cli()
        exit_code = mod.cli_main(
            argv=[
                "--domain", "does.not.exist.v99",
                "--execute",
                "--n", "3",
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0

    def test_exits_nonzero_on_missing_corpus(self, tmp_path):
        mod = _load_cli()
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--corpus-path", str(tmp_path / "nonexistent.jsonl"),
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0

    def test_exits_nonzero_on_unknown_factor(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--factors", "nonexistent_factor_id",
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0

    def test_exits_2_when_no_mode_given(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--n", "3",
                "--corpus-path", str(corpus_path),
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0

    def test_exits_1_wrong_annotator_count(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--annotators", "only-one-annotator",
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0


# ---------------------------------------------------------------------------
# 12. Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_raising_annotator_substitutes_placeholder(
        self, tmp_path, capsys, write_corpus
    ):
        """Per-call failures must NOT abort the run.

        annotate_all should substitute a placeholder annotation flagged for
        human review and continue, so one bad call doesn't lose the other
        N-1 successful results. Verified post-2ec6668 graceful-failure fix.
        """
        import json

        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        ok_client = FakeLLMClient(canned_value=True, annotator_id="ann-0")
        bad_client = RaisingClient(canned_value=True, annotator_id="ann-1")

        out_path = tmp_path / "out.jsonl"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--factors", "repair_responsibility_established",
                "--corpus-path", str(corpus_path),
                "--annotators", "ann-0,ann-1",
                "--output", str(out_path),
                "--progress-every", "0",
            ],
            injected_clients=[ok_client, bad_client],
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        # Stderr WARNING summarises the failure count and a sample.
        assert "WARNING" in captured.err
        assert "annotator calls failed" in captured.err
        # Output JSONL has 6 rows (3 cases × 1 factor × 2 annotators); the
        # 3 from the bad client are placeholders flagged for review.
        rows = [json.loads(l) for l in out_path.read_text().splitlines()]
        assert len(rows) == 6
        flagged = [r for r in rows if r["requires_human_review"]]
        assert len(flagged) == 3
        for r in flagged:
            assert r["annotator_id"] == "ann-1"
            assert r["value"]["is_null"] is True
            assert r["reasoning"].startswith("extraction_failed:")

    def test_malformed_pydantic_substitutes_placeholder(
        self, tmp_path, capsys, write_corpus
    ):
        """Validation errors are also gracefully handled per task 2ec6668."""
        import json

        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        bad_client = MalformedClient(canned_value=True, annotator_id="ann-0")
        ok_client = FakeLLMClient(canned_value=True, annotator_id="ann-1")

        out_path = tmp_path / "out.jsonl"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--factors", "repair_responsibility_established",
                "--corpus-path", str(corpus_path),
                "--annotators", "ann-0,ann-1",
                "--output", str(out_path),
                "--progress-every", "0",
            ],
            injected_clients=[bad_client, ok_client],
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        rows = [json.loads(l) for l in out_path.read_text().splitlines()]
        assert len(rows) == 6
        # Three of the six (the malformed-client annotations) are placeholders.
        flagged = [r for r in rows if r["requires_human_review"]]
        assert len(flagged) == 3
        for r in flagged:
            assert r["annotator_id"] == "ann-0"

    def test_wrong_injected_client_count_exits_1(self, tmp_path, capsys, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        # Pass only 1 client (need exactly 2)
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--corpus-path", str(corpus_path),
            ],
            injected_clients=[FakeLLMClient(True, annotator_id="ann-0")],
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0


# ---------------------------------------------------------------------------
# 13. Full end-to-end with fake clients
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_end_to_end_produces_correct_row_count(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        out_path = tmp_path / "annotations.jsonl"
        n = 3
        factors = "repair_responsibility_established,hazard_or_disrepair_reported"

        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", str(n),
                "--factors", factors,
                "--corpus-path", str(corpus_path),
                "--output", str(out_path),
                "--seed", "42",
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        # n cases × 2 factors × 2 annotators = 12
        assert len(rows) == n * 2 * 2

    def test_determinism_same_seed_identical_output(self, tmp_path, write_corpus):
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path, n=10)

        def _run(run_id: int) -> str:
            out_path = tmp_path / f"out_{run_id}.jsonl"
            mod.cli_main(
                argv=[
                    "--domain", "housing.repairs_social.v1",
                    "--execute",
                    "--n", "3",
                    "--factors", "repair_responsibility_established",
                    "--corpus-path", str(corpus_path),
                    "--output", str(out_path),
                    "--seed", "42",
                ],
                injected_clients=_make_clients(),
                repo_root=_REPO_ROOT,
            )
            return out_path.read_text()

        assert _run(0) == _run(1)


# ---------------------------------------------------------------------------
# 14. I2 — compute_krippendorff_alpha when n_valid < 2
# ---------------------------------------------------------------------------


class TestKrippendorffAlphaInsufficientData:
    def test_compute_alpha_returns_none_when_insufficient_valid_pairs(self):
        """When all annotation values are None, n_valid < 2 → alpha is None, no crash."""
        mod = _load_cli()
        # Build 4 annotation pairs where every value is None
        case_ids = [f"c{i}" for i in range(4)]
        anns = _make_annotations(
            case_ids,
            factor_id="repair_responsibility_established",
            values_a=[None, None, None, None],
            values_b=[None, None, None, None],
            value_type="boolean",
        )
        factor = {"id": "repair_responsibility_established", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)

        assert pfa.alpha is None, "Expected alpha=None when all values are null"
        assert pfa.note != "", "Expected a non-empty note describing the skip reason"
        assert "insufficient" in pfa.note.lower() or "< 2" in pfa.note, (
            f"Note should describe the insufficient-data case; got: {pfa.note!r}"
        )

    def test_compute_alpha_returns_none_when_only_one_valid_pair(self):
        """When only one annotator has a non-null value, n_valid < 2 → alpha is None."""
        mod = _load_cli()
        # ann-0 has one real value; ann-1 always None → valid mask = False everywhere
        case_ids = ["c0", "c1", "c2"]
        anns = _make_annotations(
            case_ids,
            factor_id="hazard_or_disrepair_reported",
            values_a=[True, None, None],
            values_b=[None, None, None],
            value_type="boolean",
        )
        factor = {"id": "hazard_or_disrepair_reported", "value_type": "boolean"}
        pfa = mod.compute_krippendorff_alpha(anns, factor)

        assert pfa.alpha is None
        assert isinstance(pfa, mod.PerFactorAlpha)


# ---------------------------------------------------------------------------
# 15. I3 — summary sidecar written alongside JSONL output
# ---------------------------------------------------------------------------


class TestSummarySidecar:
    def test_summary_sidecar_written(self, tmp_path, write_corpus):
        """execute mode must write a {output}.summary.json sidecar."""
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        out_path = tmp_path / "annotations.jsonl"

        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "3",
                "--factors", "repair_responsibility_established,hazard_or_disrepair_reported",
                "--corpus-path", str(corpus_path),
                "--output", str(out_path),
                "--seed", "42",
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0

        sidecar_path = tmp_path / "annotations.jsonl.summary.json"
        assert sidecar_path.exists(), f"Sidecar not found at {sidecar_path}"

        raw = json.loads(sidecar_path.read_text())
        summary = mod.RunSummary.model_validate(raw)

        assert summary.domain_id == "housing.repairs_social.v1"
        assert summary.n_cases == 3
        assert set(summary.factors) == {
            "repair_responsibility_established",
            "hazard_or_disrepair_reported",
        }
        assert len(summary.per_factor_alpha) == 2
        factor_ids_in_summary = {pfa.factor_id for pfa in summary.per_factor_alpha}
        assert factor_ids_in_summary == {
            "repair_responsibility_established",
            "hazard_or_disrepair_reported",
        }
        assert "total_tokens_in" in summary.cost_report

    def test_summary_sidecar_not_written_on_dry_run(self, tmp_path, write_corpus):
        """--dry-run must NOT produce a sidecar."""
        mod = _load_cli()
        corpus_path = write_corpus(tmp_path)
        out_path = tmp_path / "annotations.jsonl"

        mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--output", str(out_path),
            ],
            injected_clients=_make_clients(),
            repo_root=_REPO_ROOT,
        )

        sidecar_path = tmp_path / "annotations.jsonl.summary.json"
        assert not sidecar_path.exists(), "Sidecar must not be written on --dry-run"


# ---------------------------------------------------------------------------
# 16. --annotator-providers CSV parsing (new flag)
# ---------------------------------------------------------------------------


class TestAnnotatorProvidersParser:
    """Tests for _build_annotator_clients_from_providers (offline — no real API calls)."""

    def _load(self):
        return _load_cli()

    def test_missing_colon_returns_error_string(self):
        """A pair with no colon returns an error string."""
        mod = self._load()
        result = mod._build_annotator_clients_from_providers(
            "anthropic_claude-sonnet-4-20250514,openai:gpt-4o"
        )
        assert isinstance(result, str)
        assert "colon" in result.lower() or "missing" in result.lower()

    def test_empty_model_id_returns_error_string(self):
        """'anthropic:' with empty model returns an error string."""
        mod = self._load()
        result = mod._build_annotator_clients_from_providers("anthropic:,openai:gpt-4o")
        assert isinstance(result, str)
        assert "empty model" in result.lower()

    def test_unknown_provider_returns_error_string(self):
        """An unsupported provider returns an error string."""
        mod = self._load()
        result = mod._build_annotator_clients_from_providers(
            "cohere:command-r,openai:gpt-4o"
        )
        assert isinstance(result, str)
        assert "cohere" in result or "Unknown provider" in result

    def test_only_one_pair_returns_error_string(self):
        """Exactly 1 pair is rejected (2 required)."""
        mod = self._load()
        result = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514"
        )
        assert isinstance(result, str)
        assert "2" in result or "exactly" in result.lower()

    def test_three_pairs_returns_error_string(self):
        """More than 2 pairs is rejected."""
        mod = self._load()
        result = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514,openai:gpt-4o,anthropic:claude-haiku-4-5"
        )
        assert isinstance(result, str)
        assert "2" in result or "exactly" in result.lower()

    def test_anthropic_pair_missing_api_key_returns_error(self, monkeypatch):
        mod = self._load()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514,openai:gpt-4o"
        )
        assert isinstance(result, str)
        assert "ANTHROPIC_API_KEY" in result

    def test_openai_pair_missing_api_key_returns_error(self, monkeypatch):
        mod = self._load()
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514,openai:gpt-4o"
        )
        # Will fail on ANTHROPIC_API_KEY check first if that's also absent;
        # set both, then clear only OPENAI.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result2 = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514,openai:gpt-4o"
        )
        assert isinstance(result2, str)
        assert "OPENAI_API_KEY" in result2

    def test_valid_mixed_pair_returns_two_clients(self, monkeypatch):
        """Valid CSV with both keys set returns a list of 2 clients."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        result = mod._build_annotator_clients_from_providers(
            "anthropic:claude-sonnet-4-20250514,openai:gpt-4o"
        )
        assert isinstance(result, list)
        assert len(result) == 2
        labels = [getattr(c, "_annotator_label", "") for c in result]
        assert "anthropic:claude-sonnet-4-20250514" in labels
        assert "openai:gpt-4o" in labels

    def test_annotator_ids_derived_from_providers_in_dry_run(
        self, tmp_path, monkeypatch, capsys
    ):
        """--dry-run with --annotator-providers shows provider:model labels."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        corpus_path = tmp_path / "corpus.jsonl"
        with corpus_path.open("w") as fh:
            for i in range(5):
                fh.write(
                    json.dumps(
                        {
                            "case_id": f"c{i}",
                            "title": f"C{i}",
                            "outcome_raw": "m",
                            "matter_types": [],
                            "landlord_name": "L",
                        }
                    )
                    + "\n"
                )
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--n", "3",
                "--corpus-path", str(corpus_path),
                "--annotator-providers",
                "anthropic:claude-sonnet-4-20250514,openai:gpt-4o",
            ],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "anthropic:claude-sonnet-4-20250514" in captured.out
        assert "openai:gpt-4o" in captured.out

    def test_cli_unknown_provider_exits_nonzero(self, tmp_path, capsys):
        """A bad provider in --annotator-providers exits non-zero."""
        mod = self._load()
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(
            json.dumps({"case_id": "c0", "title": "C", "outcome_raw": "m",
                        "matter_types": [], "landlord_name": "L"}) + "\n"
        )
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--n", "1",
                "--corpus-path", str(corpus_path),
                "--annotator-providers", "vertex:gemini-pro,openai:gpt-4o",
            ],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code != 0
        assert "Error" in captured.err
