"""Snapshot-style assertions for the extraction prompt content.

Task 13 added a Housing Ombudsman determination ontology block to
``EXTRACTION_SYSTEM_PROMPT`` and bumped ``PROMPT_PACK_VERSION``. These
tests pin the new content so regressions surface here.
"""
from __future__ import annotations


def test_extraction_prompt_includes_determination_ontology():
    from eval.auto_label.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

    assert "Housing Ombudsman determination ontology" in EXTRACTION_SYSTEM_PROMPT
    for value in (
        "maladministration",
        "severe_maladministration",
        "service_failure",
        "reasonable_redress",
        "no_maladministration",
        "outside_jurisdiction",
        "resolved_with_intervention",
    ):
        assert value in EXTRACTION_SYSTEM_PROMPT, value


def test_extraction_prompt_includes_amount_split_guidance():
    from eval.auto_label.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

    for field in (
        "amount_ordered_now_gbp",
        "amount_previously_offered_gbp",
        "amount_global_unapportioned_gbp",
    ):
        assert field in EXTRACTION_SYSTEM_PROMPT, field


def test_extraction_prompt_includes_overall_winner_legacy_mapping():
    from eval.auto_label.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

    assert "overall_winner_legacy" in EXTRACTION_SYSTEM_PROMPT
    # The deterministic mapping must mention all three winner buckets.
    assert "tenant" in EXTRACTION_SYSTEM_PROMPT
    assert "landlord" in EXTRACTION_SYSTEM_PROMPT
    assert "split" in EXTRACTION_SYSTEM_PROMPT


def test_extraction_prompt_includes_determination_per_complaint():
    from eval.auto_label.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

    assert "determination_per_complaint" in EXTRACTION_SYSTEM_PROMPT
    assert "complaint_label" in EXTRACTION_SYSTEM_PROMPT


def test_prompt_pack_version_bumped():
    from eval.auto_label.prompts.extraction import PROMPT_PACK_VERSION

    assert PROMPT_PACK_VERSION == "1.1.0"


def test_prompt_template_hash_stable_and_well_formed():
    from eval.auto_label.prompts.extraction import prompt_template_hash

    h1 = prompt_template_hash()
    h2 = prompt_template_hash()
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_output_format_remains_last_paragraph():
    """The new ontology block must precede the 'Output format' instruction
    so the labeler still reads the JSON-output contract last."""
    from eval.auto_label.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

    ontology_idx = EXTRACTION_SYSTEM_PROMPT.find(
        "Housing Ombudsman determination ontology"
    )
    output_idx = EXTRACTION_SYSTEM_PROMPT.find("Output format:")
    assert ontology_idx != -1
    assert output_idx != -1
    assert ontology_idx < output_idx
