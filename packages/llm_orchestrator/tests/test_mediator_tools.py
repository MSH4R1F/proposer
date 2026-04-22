"""Tests for the mediator ToolSet (calculate_zopa, calculate_counter_range, get_cost_benefit).

Covers schema emission, dispatch happy paths, edge cases (clamping, fallbacks),
error paths (missing prediction, invalid role), and ToolSet routing.
"""
from __future__ import annotations

import pytest

from ..agent_loop.context import ToolContext
from ..agent_loop.tool import UnknownToolError
from ..agent_loop.trace import TraceLogger
from ..models.prediction_v2 import OutcomeType, PredictionResult
from ..tools.mediator import (
    MEDIATOR_TOOLS,
    calculate_counter_range,
    calculate_zopa,
    get_cost_benefit,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _ctx(prediction: PredictionResult = None) -> ToolContext:
    ctx = ToolContext(prediction=prediction)
    ctx.trace_logger = TraceLogger.no_op()
    return ctx


def _prediction(
    *,
    settlement_range=None,
    tenant_recovery_amount=None,
    deposit_at_stake=None,
) -> PredictionResult:
    return PredictionResult(
        case_id="test-001",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.65,
        predicted_settlement_range=settlement_range,
        tenant_recovery_amount=tenant_recovery_amount,
        deposit_at_stake=deposit_at_stake,
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_calculate_zopa_schema() -> None:
    schema = calculate_zopa.to_anthropic_schema()
    assert schema["name"] == "calculate_zopa"
    assert isinstance(schema["description"], str) and schema["description"]
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    # ZopaArgs has no fields — properties should be absent or empty
    assert input_schema.get("properties", {}) == {}


def test_calculate_counter_range_schema() -> None:
    schema = calculate_counter_range.to_anthropic_schema()
    assert schema["name"] == "calculate_counter_range"
    assert isinstance(schema["description"], str) and schema["description"]
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    props = input_schema["properties"]
    assert "current_offer" in props
    assert "role" in props
    required = input_schema.get("required", [])
    assert "current_offer" in required
    assert "role" in required


def test_get_cost_benefit_schema() -> None:
    schema = get_cost_benefit.to_anthropic_schema()
    assert schema["name"] == "get_cost_benefit"
    assert isinstance(schema["description"], str) and schema["description"]
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    props = input_schema["properties"]
    assert "role" in props
    required = input_schema.get("required", [])
    assert "role" in required


# ---------------------------------------------------------------------------
# Dispatch tests — calculate_zopa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_zopa_happy_path_with_settlement_range() -> None:
    pred = _prediction(settlement_range=(200.0, 400.0))
    ctx = _ctx(pred)
    result = await calculate_zopa.dispatch(ctx, {})
    assert result.is_error is False
    assert result.model_payload == {"min": 200.0, "max": 400.0, "center": 300.0}


@pytest.mark.asyncio
async def test_calculate_zopa_tenant_recovery_fallback() -> None:
    # base=100, spread=max(10, 25)=25, lower=max(75,0)=75, upper=125, center=100
    pred = _prediction(tenant_recovery_amount=100.0)
    ctx = _ctx(pred)
    result = await calculate_zopa.dispatch(ctx, {})
    assert result.is_error is False
    payload = result.model_payload
    assert payload["min"] == 75.0
    assert payload["max"] == 125.0
    assert payload["center"] == 100.0


@pytest.mark.asyncio
async def test_calculate_zopa_deposit_at_stake_fallback() -> None:
    # deposit=400, base=200, spread=max(30, 25)=30, lower=max(170,0)=170, upper=230, center=200
    pred = _prediction(deposit_at_stake=400.0)
    ctx = _ctx(pred)
    result = await calculate_zopa.dispatch(ctx, {})
    assert result.is_error is False
    payload = result.model_payload
    assert payload["min"] == 170.0
    assert payload["max"] == 230.0
    assert payload["center"] == 200.0


@pytest.mark.asyncio
async def test_calculate_zopa_no_data_returns_zeros() -> None:
    pred = _prediction()
    ctx = _ctx(pred)
    result = await calculate_zopa.dispatch(ctx, {})
    assert result.is_error is False
    assert result.model_payload == {"min": 0.0, "max": 0.0, "center": 0.0}


# ---------------------------------------------------------------------------
# Dispatch tests — calculate_counter_range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_counter_range_tenant_within_zopa() -> None:
    # zopa=(300, 600), tenant offer=500 → min=max(500,300)=500, max=600, center=550
    pred = _prediction(settlement_range=(300.0, 600.0))
    ctx = _ctx(pred)
    result = await calculate_counter_range.dispatch(
        ctx, {"current_offer": 500.0, "role": "tenant"}
    )
    assert result.is_error is False
    assert result.model_payload == {"min": 500.0, "max": 600.0, "center": 550.0}


@pytest.mark.asyncio
async def test_calculate_counter_range_landlord_within_zopa() -> None:
    # zopa=(300, 600), landlord offer=400 → min=300, max=min(400,600)=400, center=350
    pred = _prediction(settlement_range=(300.0, 600.0))
    ctx = _ctx(pred)
    result = await calculate_counter_range.dispatch(
        ctx, {"current_offer": 400.0, "role": "landlord"}
    )
    assert result.is_error is False
    assert result.model_payload == {"min": 300.0, "max": 400.0, "center": 350.0}


@pytest.mark.asyncio
async def test_calculate_counter_range_tenant_clamp_above_zopa() -> None:
    # zopa=(300, 600), tenant offer=700 → min=max(700,300)=700 > max=600, clamp both to 600
    pred = _prediction(settlement_range=(300.0, 600.0))
    ctx = _ctx(pred)
    result = await calculate_counter_range.dispatch(
        ctx, {"current_offer": 700.0, "role": "tenant"}
    )
    assert result.is_error is False
    payload = result.model_payload
    assert payload["min"] == 600.0
    assert payload["max"] == 600.0


# ---------------------------------------------------------------------------
# Dispatch tests — get_cost_benefit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cost_benefit_tenant_role() -> None:
    pred = _prediction(settlement_range=(200.0, 400.0))
    ctx = _ctx(pred)
    result = await get_cost_benefit.dispatch(ctx, {"role": "tenant"})
    assert result.is_error is False
    payload = result.model_payload
    assert isinstance(payload, dict)
    assert payload["party_role"] == "tenant"
    assert payload["settlement_framing"]  # non-empty string


@pytest.mark.asyncio
async def test_get_cost_benefit_landlord_role() -> None:
    pred = _prediction(settlement_range=(200.0, 400.0))
    ctx = _ctx(pred)
    result = await get_cost_benefit.dispatch(ctx, {"role": "landlord"})
    assert result.is_error is False
    payload = result.model_payload
    assert payload["party_role"] == "landlord"
    assert payload["settlement_framing"]


@pytest.mark.asyncio
async def test_get_cost_benefit_invalid_role_returns_error() -> None:
    # Pydantic's Literal validation fires before the function body
    pred = _prediction(settlement_range=(200.0, 400.0))
    ctx = _ctx(pred)
    result = await MEDIATOR_TOOLS.dispatch("get_cost_benefit", {"role": "admin"}, ctx)
    assert result.is_error is True


# ---------------------------------------------------------------------------
# Missing prediction error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_prediction_calculate_zopa_returns_error() -> None:
    ctx = _ctx()  # no prediction
    result = await calculate_zopa.dispatch(ctx, {})
    assert result.is_error is True
    error = result.model_payload
    assert isinstance(error, dict)
    assert "prediction" in error.get("error", "").lower()


@pytest.mark.asyncio
async def test_missing_prediction_calculate_counter_range_returns_error() -> None:
    ctx = _ctx()
    result = await calculate_counter_range.dispatch(
        ctx, {"current_offer": 300.0, "role": "tenant"}
    )
    assert result.is_error is True
    assert "prediction" in result.model_payload.get("error", "").lower()


@pytest.mark.asyncio
async def test_missing_prediction_get_cost_benefit_returns_error() -> None:
    ctx = _ctx()
    result = await get_cost_benefit.dispatch(ctx, {"role": "tenant"})
    assert result.is_error is True
    assert "prediction" in result.model_payload.get("error", "").lower()


# ---------------------------------------------------------------------------
# ToolSet tests
# ---------------------------------------------------------------------------


def test_mediator_tools_has_three_tools() -> None:
    assert len(MEDIATOR_TOOLS.tools) == 3
    names = {t.name for t in MEDIATOR_TOOLS.tools}
    assert names == {"calculate_zopa", "calculate_counter_range", "get_cost_benefit"}


def test_mediator_tools_anthropic_schemas_returns_three() -> None:
    schemas = MEDIATOR_TOOLS.anthropic_schemas()
    assert len(schemas) == 3
    schema_names = {s["name"] for s in schemas}
    assert schema_names == {"calculate_zopa", "calculate_counter_range", "get_cost_benefit"}


@pytest.mark.asyncio
async def test_mediator_tools_dispatch_unknown_tool_raises() -> None:
    ctx = _ctx()
    with pytest.raises(UnknownToolError):
        await MEDIATOR_TOOLS.dispatch("unknown_tool", {}, ctx)
