"""TDD tests for scripts/eval/factor_catalog_review.py — §22.1 LLM panel.

All tests are offline: no real LLM calls, no network I/O.
The fake BaseLLMClient returns canned PanelistReview JSON.

Run with:
    pytest scripts/eval/tests/test_factor_catalog_review.py -v
from the repo root.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path bootstrap so we can import scripts/eval/factor_catalog_review.py
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_SCRIPTS))

# Add packages/ parent dir so `import llm_orchestrator` (and siblings) resolve.
_PACKAGES = str(_REPO_ROOT / "packages")
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)


T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Lazy module loader (avoids registering the module too early)
# ---------------------------------------------------------------------------


def _load_cli():
    """Load factor_catalog_review as a module; re-use across the session."""
    key = "factor_catalog_review"
    if key in sys.modules:
        existing = sys.modules[key]
        # Only re-use if it loaded successfully (has the expected attribute).
        if hasattr(existing, "REVIEWER_PROMPT"):
            return existing
        # Previous import failed — evict and retry.
        del sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _SCRIPTS / "factor_catalog_review.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

FACTORS_3 = ["repair_responsibility_established", "hazard_or_disrepair_reported", "landlord_notice_established"]

def _make_finding(factor_id: str, *, labelable=True, definition_clear=True,
                  polarity_correct=True, authority_grounded=True,
                  redundant_with=None, flags=None):
    return {
        "factor_id": factor_id,
        "labelable_from_narrative": labelable,
        "definition_clear": definition_clear,
        "polarity_correct": polarity_correct,
        "authority_grounded": authority_grounded,
        "redundant_with": redundant_with or [],
        "flags": flags or [],
    }


def _canned_review(panelist_id: str, findings: list, missing=None, notes="") -> dict:
    return {
        "panelist_id": panelist_id,
        "per_factor_findings": findings,
        "missing_factors_suggested": missing or [],
        "overall_notes": notes,
    }


class FakeLLMClient:
    """Synchronous fake — generate_structured returns a canned Pydantic model."""

    def __init__(self, canned: dict, model_id: str = "fake-model"):
        self._canned = canned
        self.model = model_id
        self._stats: Dict[str, Any] = {
            "calls": 0,
            "tokens_in": 50,
            "tokens_out": 200,
            "cached_tokens_in": 0,
            "reasoning_tokens_out": 0,
            "errors": 0,
            "estimated_cost_usd": 0.0001,
            "provider": "fake",
            "model": model_id,
        }

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        response_model: Type[T],
        max_tokens: int = 4096,
    ) -> T:
        self._stats["calls"] += 1
        return response_model.model_validate(self._canned)

    async def generate(self, messages, system_prompt, max_tokens=4096, temperature=0.7) -> str:
        self._stats["calls"] += 1
        return json.dumps(self._canned)

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def reset_stats(self) -> None:
        self._stats["calls"] = 0


# ---------------------------------------------------------------------------
# 1. Import smoke test
# ---------------------------------------------------------------------------


class TestImport:
    def test_imports_cleanly(self):
        mod = _load_cli()
        assert mod is not None

    def test_pydantic_models_exist(self):
        mod = _load_cli()
        assert hasattr(mod, "PanelistReview")
        assert hasattr(mod, "FactorFinding")
        assert hasattr(mod, "PanelReview")

    def test_reviewer_prompt_constant_exists(self):
        mod = _load_cli()
        assert hasattr(mod, "REVIEWER_PROMPT")
        prompt = mod.REVIEWER_PROMPT
        assert "skeptical UK housing" in prompt
        assert "labelable_from_narrative" in prompt


# ---------------------------------------------------------------------------
# 2. Pydantic model constraints
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_factor_finding_frozen_and_forbids_extra(self):
        mod = _load_cli()
        ff = mod.FactorFinding(
            factor_id="f1",
            labelable_from_narrative=True,
            definition_clear=True,
            polarity_correct=True,
            authority_grounded=True,
            redundant_with=[],
            flags=[],
        )
        with pytest.raises(Exception):
            ff.factor_id = "mutated"  # type: ignore[misc]

    def test_panelist_review_forbids_extra(self):
        mod = _load_cli()
        with pytest.raises(Exception):
            mod.PanelistReview(
                panelist_id="x",
                per_factor_findings=[],
                missing_factors_suggested=[],
                overall_notes="",
                extra_field_not_allowed="bad",  # type: ignore[call-arg]
            )

    def test_panel_review_frozen(self):
        mod = _load_cli()
        assert mod.PanelReview.model_config.get("frozen") is True


# ---------------------------------------------------------------------------
# 3. Determination stripping
# ---------------------------------------------------------------------------


class TestDeterminationStripping:
    def test_strips_at_determination_header(self):
        mod = _load_cli()
        narrative = (
            "The resident reported damp in March 2022.\n"
            "The landlord failed to respond promptly.\n"
            "\n"
            "## Determination\n"
            "The Ombudsman finds maladministration.\n"
            "The landlord must pay £400."
        )
        stripped = mod.strip_determination(narrative)
        assert "Determination" not in stripped
        assert "The resident reported damp" in stripped

    def test_strips_at_decision_header(self):
        mod = _load_cli()
        narrative = "Background facts here.\n\n## Decision\nThe landlord wins."
        stripped = mod.strip_determination(narrative)
        assert "Decision" not in stripped
        assert "Background facts" in stripped

    def test_strips_at_findings_header(self):
        mod = _load_cli()
        text = "Some facts.\n## Findings\nResults here."
        stripped = mod.strip_determination(text)
        assert "Findings" not in stripped

    def test_strips_at_outcome_header(self):
        mod = _load_cli()
        text = "Pre-outcome text.\n## Outcome\nOutcome text."
        stripped = mod.strip_determination(text)
        assert "Outcome" not in stripped

    def test_strips_at_order_header(self):
        mod = _load_cli()
        text = "Pre-order text.\n## Order\nOrder text."
        stripped = mod.strip_determination(text)
        assert "Order" not in stripped

    def test_strips_at_compensation_header(self):
        mod = _load_cli()
        text = "Pre-compensation text.\n## Compensation\n£400 awarded."
        stripped = mod.strip_determination(text)
        assert "£400" not in stripped

    def test_case_insensitive(self):
        mod = _load_cli()
        text = "Facts.\n## DETERMINATION\nResult."
        stripped = mod.strip_determination(text)
        assert "Result" not in stripped

    def test_no_header_returns_full_text(self):
        mod = _load_cli()
        text = "Just narrative text with no determination section."
        assert mod.strip_determination(text) == text

    def test_h3_header_stripped(self):
        mod = _load_cli()
        text = "Facts.\n### Determination\nResult."
        stripped = mod.strip_determination(text)
        assert "Result" not in stripped

    def test_excerpt_capped_at_1500_chars(self):
        mod = _load_cli()
        long_text = "A" * 3000
        result = mod.cap_excerpt(long_text, max_chars=1500)
        assert len(result) <= 1500


# ---------------------------------------------------------------------------
# 4. Domain pack loading
# ---------------------------------------------------------------------------


class TestDomainPackLoading:
    def test_resolves_housing_repairs_social_v1(self):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        assert "factors" in pack
        assert len(pack["factors"]) > 0

    def test_loads_outcomes(self):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        assert "outcomes" in pack
        assert any(o["id"] == "maladministration" for o in pack["outcomes"])

    def test_loads_rubric(self):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        assert "rubric" in pack
        assert len(pack["rubric"]) > 100  # non-trivial content

    def test_unknown_domain_raises(self):
        mod = _load_cli()
        with pytest.raises(Exception):
            mod.load_domain_pack("nonexistent.domain.v99", repo_root=_REPO_ROOT)


# ---------------------------------------------------------------------------
# 5. Panel class — dispatch without real LLM
# ---------------------------------------------------------------------------


class TestPanel:
    def _make_3_clients(self, mod):
        findings = [_make_finding(f) for f in FACTORS_3]
        reviews = [
            _canned_review("p1", findings, notes="all good"),
            _canned_review("p2", findings, notes="all good"),
            _canned_review("p3", findings, notes="all good"),
        ]
        return [FakeLLMClient(r, model_id=f"fake-{i}") for i, r in enumerate(reviews)]

    def test_panel_runs_3_clients(self, tmp_path):
        mod = _load_cli()
        clients = self._make_3_clients(mod)
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        panel = mod.Panel(clients=clients)
        reviews, _cost = asyncio.run(panel.run(pack=pack, excerpts=[]))
        assert len(reviews) == 3
        for r in reviews:
            assert isinstance(r, mod.PanelistReview)

    def test_dry_run_does_not_call_client(self, tmp_path):
        mod = _load_cli()
        findings = [_make_finding(f) for f in FACTORS_3]
        canned = _canned_review("p1", findings)
        client = FakeLLMClient(canned)
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        panel = mod.Panel(clients=[client])
        # dry_run_info is now synchronous — no asyncio wrapper
        result = panel.dry_run_info(pack=pack, excerpts=[])
        assert client.get_stats()["calls"] == 0
        assert "prompt" in result or "system_prompt" in result  # returns preview dict


# ---------------------------------------------------------------------------
# 6. Aggregator — disagreement matrix
# ---------------------------------------------------------------------------


class TestAggregator:
    def _make_reviews(self, mod):
        """3 panelists; factor F1 flagged by all, F2 by 2, F3 by 1."""
        # F1: all 3 say NOT labelable
        # F2: 2 say NOT definition_clear
        # F3: 1 says NOT authority_grounded
        f1_bad = _make_finding("F1", labelable=False)
        f1_good_def = _make_finding("F1", labelable=False)
        f1_good_dup = _make_finding("F1", labelable=False)

        f2_bad = _make_finding("F2", definition_clear=False)
        f2_bad2 = _make_finding("F2", definition_clear=False)
        f2_good = _make_finding("F2")

        f3_p1_bad = _make_finding("F3", authority_grounded=False)
        f3_p2_good = _make_finding("F3")
        f3_p3_good = _make_finding("F3")

        r1 = mod.PanelistReview.model_validate(_canned_review(
            "p1", [f1_bad, f2_bad, f3_p1_bad], notes="p1"))
        r2 = mod.PanelistReview.model_validate(_canned_review(
            "p2", [f1_good_def, f2_bad2, f3_p2_good], notes="p2"))
        r3 = mod.PanelistReview.model_validate(_canned_review(
            "p3", [f1_good_dup, f2_good, f3_p3_good], notes="p3"))
        return [r1, r2, r3]

    def test_unanimous_flags_detected(self):
        mod = _load_cli()
        reviews = self._make_reviews(mod)
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()
        # F1 is flagged (labelable=False) by all 3
        unanimous = panel_review.unanimous_flags
        assert any(e["factor_id"] == "F1" for e in unanimous), \
            f"Expected F1 in unanimous flags, got: {unanimous}"

    def test_majority_flags_detected(self):
        mod = _load_cli()
        reviews = self._make_reviews(mod)
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()
        majority = panel_review.majority_flags
        assert any(e["factor_id"] == "F2" for e in majority), \
            f"Expected F2 in majority flags, got: {majority}"

    def test_single_flags_detected(self):
        mod = _load_cli()
        reviews = self._make_reviews(mod)
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()
        single = panel_review.single_flags
        assert any(e["factor_id"] == "F3" for e in single), \
            f"Expected F3 in single flags, got: {single}"

    def test_matrix_has_all_factors(self):
        mod = _load_cli()
        reviews = self._make_reviews(mod)
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()
        factor_ids = {row["factor_id"] for row in panel_review.disagreement_matrix}
        assert {"F1", "F2", "F3"}.issubset(factor_ids)


# ---------------------------------------------------------------------------
# 7. Renderer — end-to-end artifact write
# ---------------------------------------------------------------------------


class TestRenderer:
    def _make_panel_review(self, mod):
        reviews = TestAggregator()._make_reviews(mod)
        agg = mod.Aggregator(reviews)
        return agg.aggregate()

    def test_writes_artifact(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        panel_review = self._make_panel_review(mod)
        out_path = tmp_path / "test_output.md"
        renderer = mod.Renderer()
        renderer.write(
            panel_review=panel_review,
            pack=pack,
            output_path=out_path,
            date_str="2026-05-06",
        )
        assert out_path.exists()
        content = out_path.read_text()
        assert "## Panel Composition" in content or "Panel" in content
        assert "Disagreement Matrix" in content or "disagreement" in content.lower()
        assert "Unanimous" in content or "unanimous" in content.lower()

    def test_artifact_contains_cost_report(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        panel_review = self._make_panel_review(mod)
        out_path = tmp_path / "test_cost.md"
        renderer = mod.Renderer()
        renderer.write(
            panel_review=panel_review,
            pack=pack,
            output_path=out_path,
            date_str="2026-05-06",
        )
        content = out_path.read_text()
        # cost report section should mention tokens
        assert "token" in content.lower() or "cost" in content.lower()

    def test_artifact_contains_catalog_sha(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        panel_review = self._make_panel_review(mod)
        out_path = tmp_path / "test_sha.md"
        renderer = mod.Renderer()
        renderer.write(
            panel_review=panel_review,
            pack=pack,
            output_path=out_path,
            date_str="2026-05-06",
        )
        content = out_path.read_text()
        assert "sha" in content.lower() or "hash" in content.lower()


# ---------------------------------------------------------------------------
# 8. Full end-to-end with fake clients
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def _build_canned_for_real_factors(self, mod, panelist_id: str):
        """Build a canned review that covers all 15 housing.repairs_social.v1 factors."""
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        factor_ids = [f["id"] for f in pack["factors"]]
        findings = [_make_finding(fid) for fid in factor_ids]
        return _canned_review(panelist_id, findings, notes=f"Review from {panelist_id}")

    def test_end_to_end_produces_artifact(self, tmp_path):
        mod = _load_cli()
        canned_reviews = [
            self._build_canned_for_real_factors(mod, f"panelist-{i}")
            for i in range(3)
        ]
        clients = [FakeLLMClient(c, model_id=f"fake-{i}") for i, c in enumerate(canned_reviews)]
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)

        panel = mod.Panel(clients=clients)
        reviews, cost_report = asyncio.run(panel.run(pack=pack, excerpts=[]))
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate(cost_report=cost_report)

        out_path = tmp_path / "output.md"
        renderer = mod.Renderer()
        renderer.write(panel_review=panel_review, pack=pack, output_path=out_path, date_str="2026-05-06")
        assert out_path.exists()
        content = out_path.read_text()
        assert len(content) > 500

    def test_determinism_same_seed_same_output(self, tmp_path):
        """Same seed + same canned outputs → identical artifact bodies (modulo date line)."""
        mod = _load_cli()
        canned = [self._build_canned_for_real_factors(mod, f"p{i}") for i in range(3)]
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)

        def _run() -> str:
            clients = [FakeLLMClient(c, model_id=f"fake-{i}") for i, c in enumerate(canned)]
            panel = mod.Panel(clients=clients)
            reviews, cost_report = asyncio.run(panel.run(pack=pack, excerpts=[]))
            agg = mod.Aggregator(reviews)
            pr = agg.aggregate(cost_report=cost_report)
            out_path = tmp_path / f"out_{id(clients)}.md"
            renderer = mod.Renderer()
            renderer.write(panel_review=pr, pack=pack, output_path=out_path, date_str="2026-05-06")
            lines = out_path.read_text().splitlines()
            # Strip any line containing a wall-clock timestamp (iso datetime)
            return "\n".join(
                ln for ln in lines
                if not any(tok in ln for tok in ["generated_at", "Generated at", "generated at"])
            )

        run1 = _run()
        run2 = _run()
        assert run1 == run2


# ---------------------------------------------------------------------------
# 9. CLI entry-point — dry-run does not call LLM
# ---------------------------------------------------------------------------


class TestCLIDryRun:
    def test_dry_run_exits_0_and_no_llm_calls(self, tmp_path, capsys):
        mod = _load_cli()
        # Patch the factory so no real client is instantiated
        captured_calls = []

        class _SpyClient(FakeLLMClient):
            async def generate_structured(self, *a, **kw):
                captured_calls.append(1)
                return await super().generate_structured(*a, **kw)

        findings = [_make_finding(f) for f in FACTORS_3]
        canned = _canned_review("spy", findings)
        spy = _SpyClient(canned)

        out_path = tmp_path / "review.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--output", str(out_path),
                "--panelists", "1",
            ],
            injected_clients=[spy],
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        assert len(captured_calls) == 0, "dry-run must NOT call LLM"
        assert not out_path.exists(), "dry-run must NOT write artifact"

    def test_execute_mode_writes_artifact(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        factor_ids = [f["id"] for f in pack["factors"]]
        canned = _canned_review(
            "fake-model",
            [_make_finding(fid) for fid in factor_ids],
        )
        client = FakeLLMClient(canned, model_id="fake-model")

        out_path = tmp_path / "panel_review.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--output", str(out_path),
                "--panelists", "1",
                "--seed", "42",
            ],
            injected_clients=[client],
            repo_root=_REPO_ROOT,
        )
        assert exit_code == 0
        assert out_path.exists()

    def test_missing_domain_exits_nonzero(self, tmp_path, capsys):
        mod = _load_cli()
        out_path = tmp_path / "x.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "does.not.exist.v99",
                "--execute",
                "--output", str(out_path),
            ],
            injected_clients=[],
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0


# ---------------------------------------------------------------------------
# 10. C2: _BINARY_AXES drives _axes_flagged — no drift
# ---------------------------------------------------------------------------


class TestBinaryAxesDriven:
    def test_axes_flagged_matches_binary_axes_for_all_false(self):
        """When all _BINARY_AXES are False, _axes_flagged must include every one."""
        mod = _load_cli()
        # Build a finding where every binary axis is False
        finding = mod.FactorFinding(
            factor_id="test",
            labelable_from_narrative=False,
            definition_clear=False,
            polarity_correct=False,
            authority_grounded=False,
            redundant_with=[],
            flags=[],
        )
        flagged = mod._axes_flagged(finding)
        for ax in mod._BINARY_AXES:
            assert ax in flagged, f"Expected axis '{ax}' in flagged list but got: {flagged}"

    def test_axes_flagged_excludes_true_axes(self):
        """Axes that are True must NOT appear in _axes_flagged output."""
        mod = _load_cli()
        finding = mod.FactorFinding(
            factor_id="test",
            labelable_from_narrative=True,
            definition_clear=False,
            polarity_correct=True,
            authority_grounded=True,
            redundant_with=[],
            flags=[],
        )
        flagged = mod._axes_flagged(finding)
        assert "definition_clear" in flagged
        assert "labelable_from_narrative" not in flagged
        assert "polarity_correct" not in flagged
        assert "authority_grounded" not in flagged

    def test_binary_axes_covers_all_boolean_fields(self):
        """_BINARY_AXES must enumerate the same boolean fields as FactorFinding declares."""
        mod = _load_cli()
        boolean_fields = {
            name
            for name, field in mod.FactorFinding.model_fields.items()
            if field.annotation is bool
        }
        assert set(mod._BINARY_AXES) == boolean_fields, (
            f"_BINARY_AXES {mod._BINARY_AXES} does not match FactorFinding boolean fields {boolean_fields}"
        )


# ---------------------------------------------------------------------------
# 11. I1: Rendered artifact contains the full REVIEWER_PROMPT
# ---------------------------------------------------------------------------


class TestRendererPromptEmbedded:
    def test_artifact_contains_reviewer_prompt_opening(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        findings = [_make_finding(fid) for fid in [f["id"] for f in pack["factors"]]]
        reviews = [
            mod.PanelistReview.model_validate(_canned_review("p1", findings))
        ]
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()

        out_path = tmp_path / "prompt_test.md"
        renderer = mod.Renderer()
        renderer.write(
            panel_review=panel_review,
            pack=pack,
            output_path=out_path,
            date_str="2026-05-06",
        )
        content = out_path.read_text()
        # §22.1 requires the full reviewer prompt to be in the artifact
        assert "You are a skeptical UK housing/employment paralegal" in content, (
            "Rendered artifact must embed the REVIEWER_PROMPT opening phrase"
        )

    def test_artifact_reviewer_prompt_section_present(self, tmp_path):
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        findings = [_make_finding(fid) for fid in [f["id"] for f in pack["factors"]]]
        reviews = [
            mod.PanelistReview.model_validate(_canned_review("p1", findings))
        ]
        agg = mod.Aggregator(reviews)
        panel_review = agg.aggregate()

        out_path = tmp_path / "prompt_section.md"
        renderer = mod.Renderer()
        renderer.write(
            panel_review=panel_review,
            pack=pack,
            output_path=out_path,
            date_str="2026-05-06",
        )
        content = out_path.read_text()
        assert "## Reviewer Prompt" in content


# ---------------------------------------------------------------------------
# 12. I4: Error-path tests
# ---------------------------------------------------------------------------


class RaisingClient(FakeLLMClient):
    """Client that raises RuntimeError on generate_structured."""

    async def generate_structured(self, *args, **kwargs):
        raise RuntimeError("Simulated LLM failure for panelist test")


class MalformedClient(FakeLLMClient):
    """Client that returns JSON missing required Pydantic fields."""

    async def generate_structured(self, messages, system_prompt, response_model, max_tokens=4096):
        self._stats["calls"] += 1
        # Missing all required fields → model_validate will raise
        return response_model.model_validate({"panelist_id": "bad-panelist"})


class TestErrorPaths:
    def _real_factor_ids(self, mod):
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        return [f["id"] for f in pack["factors"]]

    def test_raising_client_exits_nonzero_with_clear_error(self, tmp_path, capsys):
        """If generate_structured raises, CLI must exit non-zero with panelist context."""
        mod = _load_cli()
        factor_ids = self._real_factor_ids(mod)
        canned = _canned_review("ok-panelist", [_make_finding(fid) for fid in factor_ids])
        # First client is fine; second raises
        ok_client = FakeLLMClient(canned, model_id="ok")
        bad_client = RaisingClient(canned, model_id="bad")

        out_path = tmp_path / "error_output.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--output", str(out_path),
                "--panelists", "2",
            ],
            injected_clients=[ok_client, bad_client],
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0
        captured = capsys.readouterr()
        assert "Error" in captured.err or "error" in captured.err.lower(), (
            f"Expected error message on stderr, got: {captured.err!r}"
        )

    def test_malformed_json_exits_nonzero(self, tmp_path, capsys):
        """If a panelist returns JSON that fails Pydantic validation, CLI exits non-zero."""
        mod = _load_cli()
        factor_ids = self._real_factor_ids(mod)
        canned = _canned_review("ok", [_make_finding(fid) for fid in factor_ids])
        bad_client = MalformedClient(canned, model_id="malformed")

        out_path = tmp_path / "malformed_output.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--output", str(out_path),
                "--panelists", "1",
            ],
            injected_clients=[bad_client],
            repo_root=_REPO_ROOT,
        )
        assert exit_code != 0

    def test_missing_raw_text_path_uses_stub(self, tmp_path):
        """load_corpus_excerpts falls back to stub for rows with missing raw_text_path."""
        mod = _load_cli()
        # Write a tiny JSONL with a row pointing at a nonexistent file
        jsonl_path = tmp_path / "mini_corpus.jsonl"
        jsonl_path.write_text(
            json.dumps({
                "case_id": "test-case-001",
                "title": "Test case title",
                "outcome_raw": "maladministration",
                "matter_types": ["repairs"],
                "landlord_name": "Test Landlord",
                "raw_text_path": "nonexistent/path/to/missing_file.txt",
            }) + "\n"
        )
        excerpts = mod.load_corpus_excerpts(n=1, seed=42, corpus_path=jsonl_path)
        # Must return exactly 1 excerpt (stub, not nothing)
        assert len(excerpts) == 1
        # Stub must include the case metadata we supplied
        assert "Test case title" in excerpts[0] or "test-case-001" in excerpts[0], (
            f"Expected stub to contain case metadata, got: {excerpts[0]!r}"
        )


# ---------------------------------------------------------------------------
# 13. M2: Stderr warning when injected_clients count < --panelists
# ---------------------------------------------------------------------------


class TestPaddingWarning:
    def test_warning_on_stderr_when_padding(self, tmp_path, capsys):
        """CLI emits a WARNING to stderr when padding clients to reach panelist count."""
        mod = _load_cli()
        pack = mod.load_domain_pack("housing.repairs_social.v1", repo_root=_REPO_ROOT)
        factor_ids = [f["id"] for f in pack["factors"]]
        canned = _canned_review("p1", [_make_finding(fid) for fid in factor_ids])
        # Only 1 client, but requesting 3 panelists → should warn
        single_client = FakeLLMClient(canned, model_id="model-0")

        out_path = tmp_path / "padded.md"
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--output", str(out_path),
                "--panelists", "3",
            ],
            injected_clients=[single_client],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "WARNING" in captured.err, (
            f"Expected WARNING in stderr when padding clients, got: {captured.err!r}"
        )
        # Warning should mention the counts
        assert "1" in captured.err and "3" in captured.err, (
            f"Expected counts (1 provided, 3 requested) in warning, got: {captured.err!r}"
        )


# ---------------------------------------------------------------------------
# 14. --panelist-providers CSV parsing (new flag)
# ---------------------------------------------------------------------------


class TestPanelistProvidersParser:
    """Tests for _build_clients_from_providers (offline — no real API calls)."""

    def _load(self):
        return _load_cli()

    def test_missing_colon_returns_error_string(self):
        """A pair with no colon should return an error string."""
        mod = self._load()
        result = mod._build_clients_from_providers("anthropic_claude-opus-4-20250514")
        assert isinstance(result, str)
        assert "colon" in result.lower() or "missing" in result.lower()

    def test_empty_model_id_returns_error_string(self):
        """A pair like 'anthropic:' (no model) should return an error string."""
        mod = self._load()
        result = mod._build_clients_from_providers("anthropic:")
        assert isinstance(result, str)
        assert "empty model" in result.lower()

    def test_unknown_provider_returns_error_string(self):
        """A pair with an unsupported provider returns an error string."""
        mod = self._load()
        result = mod._build_clients_from_providers("cohere:command-r")
        assert isinstance(result, str)
        assert "cohere" in result or "Unknown provider" in result

    def test_empty_csv_returns_error_string(self):
        """An empty or whitespace-only CSV returns an error string."""
        mod = self._load()
        result = mod._build_clients_from_providers("   ")
        assert isinstance(result, str)

    def test_anthropic_pair_missing_api_key_returns_error(self, monkeypatch):
        """anthropic: pair without ANTHROPIC_API_KEY set returns an error string."""
        mod = self._load()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = mod._build_clients_from_providers("anthropic:claude-opus-4-20250514")
        assert isinstance(result, str)
        assert "ANTHROPIC_API_KEY" in result

    def test_openai_pair_missing_api_key_returns_error(self, monkeypatch):
        """openai: pair without OPENAI_API_KEY set returns an error string."""
        mod = self._load()
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = mod._build_clients_from_providers("openai:gpt-4o")
        assert isinstance(result, str)
        assert "OPENAI_API_KEY" in result

    def test_valid_anthropic_pair_returns_client_list(self, monkeypatch):
        """With a valid ANTHROPIC_API_KEY, a single anthropic: pair returns a list."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        result = mod._build_clients_from_providers("anthropic:claude-opus-4-20250514")
        assert isinstance(result, list)
        assert len(result) == 1
        client = result[0]
        # client.model should reflect the requested model ID
        assert getattr(client, "model", None) == "claude-opus-4-20250514"
        # _panelist_label must be set for dry-run display
        assert getattr(client, "_panelist_label", None) == "anthropic:claude-opus-4-20250514"

    def test_valid_openai_pair_returns_client_list(self, monkeypatch):
        """With a valid OPENAI_API_KEY, a single openai: pair returns a list."""
        mod = self._load()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
        result = mod._build_clients_from_providers("openai:gpt-4o")
        assert isinstance(result, list)
        assert len(result) == 1
        client = result[0]
        assert getattr(client, "model", None) == "gpt-4o"
        assert getattr(client, "_panelist_label", None) == "openai:gpt-4o"

    def test_mixed_csv_returns_two_clients(self, monkeypatch):
        """Two provider:model pairs build two distinct clients."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        result = mod._build_clients_from_providers(
            "anthropic:claude-opus-4-20250514,openai:gpt-4o"
        )
        assert isinstance(result, list)
        assert len(result) == 2
        labels = [getattr(c, "_panelist_label", "") for c in result]
        assert "anthropic:claude-opus-4-20250514" in labels
        assert "openai:gpt-4o" in labels

    def test_cli_dry_run_shows_provider_model_labels(self, tmp_path, monkeypatch, capsys):
        """--dry-run with --panelist-providers shows provider:model labels in output."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--panelist-providers", "anthropic:claude-opus-4-20250514,openai:gpt-4o",
                "--output", str(tmp_path / "preview.md"),
            ],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "anthropic:claude-opus-4-20250514" in captured.out
        assert "openai:gpt-4o" in captured.out

    def test_cli_panelist_providers_overrides_panelists_count_with_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        """When --panelists and --panelist-providers both set, providers wins with a warning."""
        mod = self._load()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--dry-run",
                "--panelists", "5",  # conflicts: providers gives 2
                "--panelist-providers", "anthropic:claude-opus-4-20250514,openai:gpt-4o",
                "--output", str(tmp_path / "preview.md"),
            ],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        # Should warn that --panelists was overridden
        assert "WARNING" in captured.err or "overridden" in captured.err.lower()

    def test_cli_unknown_provider_exits_nonzero(self, tmp_path, capsys):
        """A bad provider in --panelist-providers exits non-zero with an error."""
        mod = self._load()
        exit_code = mod.cli_main(
            argv=[
                "--domain", "housing.repairs_social.v1",
                "--execute",
                "--panelist-providers", "groq:llama-3",
                "--output", str(tmp_path / "out.md"),
            ],
            repo_root=_REPO_ROOT,
        )
        captured = capsys.readouterr()
        assert exit_code != 0
        assert "Error" in captured.err
