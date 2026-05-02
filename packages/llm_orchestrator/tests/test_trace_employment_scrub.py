"""SHA-20 Phase 8: tests for employment-domain trace scrubbing.

The scrubber MUST fire only when the resolved domain family is
``employment``; other domains must see the standard ``redact_text``
output without the extra masking.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from llm_orchestrator.agent_loop.context import ToolContext
from llm_orchestrator.agent_loop.loop import (
    AgentLoop,
    AgentTurnResponse,
    _preview,
)
from llm_orchestrator.agent_loop.tool import ToolSet
from llm_orchestrator.agent_loop.trace import (
    TraceLogger,
    _scrub_employment_trace_text,
    redact_text,
)


# ---------------------------------------------------------------------------
# Direct unit tests for the scrubber
# ---------------------------------------------------------------------------


class TestEmploymentScrubber:
    def test_email_phone_postcode_masked(self):
        text = "Email me at jane@acme.co.uk or call 07123 456789. Postcode SW1A 1AA."
        out = _scrub_employment_trace_text(text)
        assert "[email]" in out
        assert "[phone]" in out
        assert "[postcode]" in out
        assert "jane@acme.co.uk" not in out
        assert "07123" not in out
        assert "SW1A 1AA" not in out

    def test_ni_number_masked(self):
        text = "NI number AB123456C is on file."
        out = _scrub_employment_trace_text(text)
        assert "[ni_number]" in out
        assert "AB123456C" not in out

    def test_party_names_masked(self):
        text = "The claimant Jane Doe alleged unfair treatment by John Smith."
        out = _scrub_employment_trace_text(
            text, party_names=["Jane Doe", "John Smith"]
        )
        assert "[person]" in out
        assert "Jane Doe" not in out
        assert "John Smith" not in out

    def test_party_names_case_insensitive(self):
        text = "jane doe was the claimant."
        out = _scrub_employment_trace_text(text, party_names=["Jane Doe"])
        assert "[person]" in out

    def test_no_party_names_leaves_text_otherwise(self):
        text = "The claimant alleged unfair treatment."
        out = _scrub_employment_trace_text(text, party_names=None)
        assert "claimant" in out

    def test_truncation_after_scrubbing(self):
        text = "x" * 600
        out = _scrub_employment_trace_text(text, max_chars=100)
        assert len(out) <= 105  # 100 + ellipsis padding


# ---------------------------------------------------------------------------
# _preview integration: family gating
# ---------------------------------------------------------------------------


class TestPreviewFamilyGating:
    def test_employment_family_applies_scrubber(self):
        text = "claimant Jane Doe with NI AB123456C lives at SW1A 1AA"
        out = _preview(
            text,
            redact=True,
            domain_family="employment",
            party_names=["Jane Doe"],
        )
        assert "[person]" in out
        assert "[ni_number]" in out
        assert "[postcode]" in out

    def test_housing_family_does_not_invoke_employment_scrubber(self):
        text = "claimant Jane Doe with NI AB123456C lives at SW1A 1AA"
        out = _preview(
            text,
            redact=True,
            domain_family="housing",
            party_names=["Jane Doe"],
        )
        # standard redaction still masks postcode/email/phone
        assert "[postcode]" in out
        # but NI and party names are NOT masked for non-employment.
        assert "AB123456C" in out
        assert "Jane Doe" in out

    def test_no_family_no_employment_scrubbing(self):
        text = "Jane Doe NI AB123456C"
        out = _preview(text, redact=True, domain_family=None, party_names=["Jane Doe"])
        assert "AB123456C" in out
        assert "Jane Doe" in out


# ---------------------------------------------------------------------------
# Loop integration: ToolContext drives gating
# ---------------------------------------------------------------------------


class _ScriptedClient:
    """Minimal AgentTurnClient stub returning a single text turn."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def run_agent_turn(self, **kwargs):
        return AgentTurnResponse(
            content_blocks=[{"type": "text", "text": self.text}],
            stop_reason="end_turn",
            tokens_in=10,
            tokens_out=20,
            model_used="fake-model",
        )


@pytest.mark.asyncio
async def test_loop_employment_traces_get_scrubbed():
    """When ctx.domain_tags['domain.family'] == 'employment', the model
    output preview stored in the trace must be scrubbed."""
    secret_text = (
        "Claimant Jane Doe (NI AB123456C, jane@acme.co.uk, SW1A 1AA) "
        "alleges unfair dismissal."
    )
    client = _ScriptedClient(secret_text)
    loop = AgentLoop(
        llm_client=client,
        tool_set=ToolSet(name="empty", tools=[]),
        max_turns=1,
    )
    ctx = ToolContext(
        request_id="req-emp",
        domain_tags={"domain.family": "employment"},
        employment_party_names=["Jane Doe"],
    )
    result = await loop.run(system_prompt="x", messages=[], ctx=ctx)
    # Find model_turn step; its preview should be scrubbed.
    model_steps = [s for s in result.trace.steps if s.kind == "model_turn"]
    assert model_steps
    preview = model_steps[0].output_preview
    assert "[person]" in preview
    assert "[ni_number]" in preview
    assert "[email]" in preview
    assert "[postcode]" in preview
    assert "Jane Doe" not in preview
    assert "AB123456C" not in preview


@pytest.mark.asyncio
async def test_loop_housing_traces_not_employment_scrubbed():
    """A housing-family trace gets standard redaction only — party names
    and NI numbers are NOT masked (they're not housing PII)."""
    text = "Jane Doe filed a deposit claim with NI AB123456C."
    client = _ScriptedClient(text)
    loop = AgentLoop(
        llm_client=client,
        tool_set=ToolSet(name="empty", tools=[]),
        max_turns=1,
    )
    ctx = ToolContext(
        request_id="req-housing",
        domain_tags={"domain.family": "housing"},
        employment_party_names=["Jane Doe"],
    )
    result = await loop.run(system_prompt="x", messages=[], ctx=ctx)
    model_steps = [s for s in result.trace.steps if s.kind == "model_turn"]
    preview = model_steps[0].output_preview
    assert "Jane Doe" in preview
    assert "AB123456C" in preview
