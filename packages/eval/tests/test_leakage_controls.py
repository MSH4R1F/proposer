"""SHA-20 Phase 7 — tests for ``packages/eval/leakage.py``.

Three control classes are exercised:

* target-source exclusion (envelope construction)
* temporal validity (cited authority post-dating decision date)
* namespace match + cross-domain guard
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from eval.leakage import (
    CrossDomainEvalRefused,
    EvalLeakageError,
    NamespaceMismatchError,
    TargetSourceExclusionError,
    TemporalLeakageError,
    assert_no_target_source_in_results,
    build_eval_filter_envelope,
    enforce_namespace_match,
    enforce_temporal_validity,
    require_eval_only_for_cross_domain,
)
from eval.schema import GoldCase
from eval.tests.conftest import gold_case_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gold(**overrides) -> GoldCase:
    return GoldCase.model_validate(gold_case_dict(**overrides))


# ---------------------------------------------------------------------------
# build_eval_filter_envelope
# ---------------------------------------------------------------------------


class TestBuildEvalFilterEnvelope:
    def test_excluded_source_ids_include_target_and_extras(self):
        gold = _gold(
            target_source_id="src-target",
            excluded_source_ids=["src-appeal", "src-related"],
        )
        env = build_eval_filter_envelope(gold)
        assert env.excluded_source_ids[0] == "src-target"
        assert "src-appeal" in env.excluded_source_ids
        assert "src-related" in env.excluded_source_ids

    def test_excluded_dedupes_when_target_repeated_in_extras(self):
        gold = _gold(
            target_source_id="src-target",
            excluded_source_ids=["src-target", "src-other"],
        )
        env = build_eval_filter_envelope(gold)
        assert env.excluded_source_ids.count("src-target") == 1
        assert "src-other" in env.excluded_source_ids

    def test_max_decision_date_matches_gold(self):
        gold = _gold(decision_date="2023-07-01")
        env = build_eval_filter_envelope(gold)
        assert env.max_decision_date == date(2023, 7, 1)

    def test_retrospective_disables_max_decision_date(self):
        gold = _gold(decision_date="2023-07-01")
        env = build_eval_filter_envelope(gold, retrospective=True)
        assert env.max_decision_date is None

    def test_envelope_defaults_cross_domain_false_eval_only_true(self):
        env = build_eval_filter_envelope(_gold())
        assert env.cross_domain_allowed is False
        assert env.eval_only is True

    def test_eval_only_cannot_be_disabled_even_with_cross_domain(self):
        # eval_only is unconditionally True regardless of caller intent.
        env = build_eval_filter_envelope(_gold(), cross_domain=True, eval_only=False)
        assert env.eval_only is True
        assert env.cross_domain_allowed is True

    def test_forum_source_kind_publisher_matter_pass_through(self):
        gold = _gold(
            forum="county_court",
            source_kind="case_decision",
            source_publisher="bailii",
            matter_type="deposit_non_protection",
            law_effective_date="2007-04-06",
        )
        env = build_eval_filter_envelope(gold)
        assert env.forum is not None and env.forum.value == "county_court"
        assert env.source_kind.value == "case_decision"
        assert env.source_publisher.value == "bailii"
        assert env.matter_type == "deposit_non_protection"
        assert env.as_of_date == date(2007, 4, 6)

    def test_unknown_enum_values_silently_drop_to_none(self):
        gold = _gold(
            forum="totally_made_up_forum",
            source_kind="not_a_real_kind",
            source_publisher="bogus",
        )
        env = build_eval_filter_envelope(gold)
        assert env.forum is None
        assert env.source_kind is None
        assert env.source_publisher is None


# ---------------------------------------------------------------------------
# enforce_temporal_validity
# ---------------------------------------------------------------------------


@dataclass
class _Citation:
    name: str
    cited_date: date


class TestEnforceTemporalValidity:
    def test_no_violations_when_all_authorities_pre_date_decision(self):
        gold = _gold(decision_date="2023-07-01")
        cits = [
            _Citation("Older Auth", date(2020, 1, 1)),
            _Citation("Same Day", date(2023, 7, 1)),
        ]
        violations = enforce_temporal_validity(cits, gold)
        assert violations == []

    def test_raises_when_authority_post_dates_decision(self):
        gold = _gold(decision_date="2023-07-01")
        cits = [_Citation("Future Auth", date(2024, 1, 1))]
        with pytest.raises(TemporalLeakageError, match="Future Auth"):
            enforce_temporal_validity(cits, gold)

    def test_returns_violations_without_raising_when_flag_set(self):
        gold = _gold(decision_date="2023-07-01")
        cits = [
            _Citation("F1", date(2024, 1, 1)),
            _Citation("F2", date(2025, 6, 1)),
        ]
        violations = enforce_temporal_validity(cits, gold, raise_on_violation=False)
        assert len(violations) == 2
        assert {v.authority_name for v in violations} == {"F1", "F2"}

    def test_dict_citations_are_supported(self):
        gold = _gold(decision_date="2023-07-01")
        cits = [{"name": "Future", "cited_date": "2024-05-01"}]
        with pytest.raises(TemporalLeakageError):
            enforce_temporal_validity(cits, gold)

    def test_temporal_leakage_error_is_eval_leakage_error(self):
        assert issubclass(TemporalLeakageError, EvalLeakageError)


# ---------------------------------------------------------------------------
# enforce_namespace_match
# ---------------------------------------------------------------------------


def _spec_with_namespaces(*ns_ids: str):
    """Stub DomainSpec-shaped object; only ``retrieval_namespaces`` is read."""
    namespaces = [SimpleNamespace(namespace_id=n) for n in ns_ids]
    return SimpleNamespace(id="dom.test.v1", retrieval_namespaces=namespaces)


class TestEnforceNamespaceMatch:
    def test_noop_when_gold_has_no_namespace_id(self):
        gold = _gold()
        spec = _spec_with_namespaces("housing_deposit_v1_legacy")
        # Should not raise.
        enforce_namespace_match(spec, gold)

    def test_passes_when_namespace_is_declared(self):
        gold = _gold(retrieval_namespace_id="housing_deposit_v1_legacy")
        spec = _spec_with_namespaces("housing_deposit_v1_legacy", "other_ns")
        enforce_namespace_match(spec, gold)

    def test_raises_when_namespace_not_declared(self):
        gold = _gold(retrieval_namespace_id="some_other_ns")
        spec = _spec_with_namespaces("housing_deposit_v1_legacy")
        with pytest.raises(NamespaceMismatchError, match="some_other_ns"):
            enforce_namespace_match(spec, gold)


# ---------------------------------------------------------------------------
# require_eval_only_for_cross_domain
# ---------------------------------------------------------------------------


class TestRequireEvalOnlyForCrossDomain:
    def test_cross_domain_requires_eval_only(self):
        args = SimpleNamespace(cross_domain=True, eval_only=False)
        with pytest.raises(CrossDomainEvalRefused):
            require_eval_only_for_cross_domain(args)

    def test_cross_domain_with_eval_only_passes(self):
        args = SimpleNamespace(cross_domain=True, eval_only=True)
        require_eval_only_for_cross_domain(args)  # no raise

    def test_no_cross_domain_passes_regardless_of_eval_only(self):
        require_eval_only_for_cross_domain(
            SimpleNamespace(cross_domain=False, eval_only=False)
        )
        require_eval_only_for_cross_domain(
            SimpleNamespace(cross_domain=False, eval_only=True)
        )

    def test_argparse_namespace_compatible(self):
        # The contract is duck-typed; argparse Namespace must work too.
        import argparse

        ns = argparse.Namespace(cross_domain=True, eval_only=False)
        with pytest.raises(CrossDomainEvalRefused):
            require_eval_only_for_cross_domain(ns)


# ---------------------------------------------------------------------------
# assert_no_target_source_in_results (post-retrieval sanity)
# ---------------------------------------------------------------------------


class TestAssertNoTargetSourceInResults:
    def test_clean_results_pass(self):
        gold = _gold(target_source_id="src-target")
        results = [{"source_id": "src-other"}, {"source_id": "src-third"}]
        report = assert_no_target_source_in_results(results, gold)
        assert report.is_clean

    def test_target_source_leak_raises(self):
        gold = _gold(target_source_id="src-target")
        results = [{"source_id": "src-target"}]
        with pytest.raises(TargetSourceExclusionError, match="src-target"):
            assert_no_target_source_in_results(results, gold)
