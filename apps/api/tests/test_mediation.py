import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


DISPUTE_ID = "disp-1"
TENANT_SESSION = "tenant-sess-1"
LANDLORD_SESSION = "landlord-sess-1"


async def _start(mediation_service):
    return await mediation_service.start_mediation(DISPUTE_ID, TENANT_SESSION)


@pytest.mark.asyncio
async def test_start_mediation_happy_path(mediation_service):
    result = await _start(mediation_service)

    assert result["status"] == "active_negotiation"
    assert result["initial_message"]["message_type"] == "ai_mediator"
    assert len(mediation_service._mediations[DISPUTE_ID].messages) >= 1


@pytest.mark.asyncio
async def test_start_mediation_no_prediction(mediation_service):
    mock_prediction_service = MagicMock()
    mock_prediction_service.list_predictions_for_case = AsyncMock(return_value=[])
    mock_prediction_service.get_prediction = AsyncMock(return_value=None)

    with patch(
        "apps.api.src.services.prediction_service.get_prediction_service",
        return_value=mock_prediction_service,
    ):
        with pytest.raises(ValueError, match="Prediction required"):
            await _start(mediation_service)


@pytest.mark.asyncio
async def test_get_expectation_data_tenant(mediation_service):
    result = await mediation_service.get_expectation_data(DISPUTE_ID, TENANT_SESSION)

    assert result["party_role"] == "tenant"
    assert result["prediction"]["prediction_id"] == "pred-1"


@pytest.mark.asyncio
async def test_get_expectation_data_landlord(mediation_service):
    result = await mediation_service.get_expectation_data(DISPUTE_ID, LANDLORD_SESSION)

    assert result["party_role"] == "landlord"
    assert result["prediction"]["prediction_id"] == "pred-1"


@pytest.mark.asyncio
async def test_send_message_triggers_ai(mediation_service):
    await _start(mediation_service)
    result = await mediation_service.add_message(
        DISPUTE_ID, TENANT_SESSION, "Opening offer"
    )

    assert "ai_response" in result
    assert result["ai_response"]["sender_role"] == "ai_mediator"


@pytest.mark.asyncio
async def test_submit_valid_offer(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)

    assert offer.amount == 500
    assert offer.status.value == "pending"


@pytest.mark.asyncio
async def test_submit_invalid_offer_negative(mediation_service):
    await _start(mediation_service)

    with pytest.raises(ValueError, match="within 0 and"):
        await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, -100)


@pytest.mark.asyncio
async def test_submit_invalid_offer_exceeds_deposit(mediation_service):
    await _start(mediation_service)

    with pytest.raises(ValueError, match="within 0 and"):
        await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 5000)


@pytest.mark.asyncio
async def test_submit_offer_can_exceed_deposit_when_prediction_range_supports_it(
    mediation_service,
    test_prediction,
):
    test_prediction["predicted_settlement_range"] = [1500, 3000]
    await _start(mediation_service)

    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 2500)

    assert offer.amount == 2500
    assert offer.status.value == "pending"


@pytest.mark.asyncio
async def test_submit_offer_zero(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 0)

    assert offer.amount == 0
    assert offer.status.value == "pending"


@pytest.mark.asyncio
async def test_accept_offer_settles(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)

    result = await mediation_service.respond_to_offer(
        DISPUTE_ID,
        LANDLORD_SESSION,
        offer.id,
        "accept",
    )

    assert result["action"] == "accept"
    assert mediation_service._mediations[DISPUTE_ID].status.value == "settled"


@pytest.mark.asyncio
async def test_reject_offer(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)

    result = await mediation_service.respond_to_offer(
        DISPUTE_ID,
        LANDLORD_SESSION,
        offer.id,
        "reject",
    )

    assert result["action"] == "reject"
    assert (
        mediation_service._mediations[DISPUTE_ID].status.value == "active_negotiation"
    )


@pytest.mark.asyncio
async def test_counter_offer(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)

    result = await mediation_service.respond_to_offer(
        DISPUTE_ID,
        LANDLORD_SESSION,
        offer.id,
        "counter",
        counter_amount=700,
    )

    assert result["action"] == "counter"
    assert result["counter_amount"] == 700
    assert result["offer"]["amount"] == 700


@pytest.mark.asyncio
async def test_get_messages_polling(mediation_service):
    """get_messages returns a list of message dicts; offers are fetched separately
    via get_session() in the unified contract."""
    await _start(mediation_service)
    all_messages = await mediation_service.get_messages(DISPUTE_ID)
    since_timestamp = all_messages[0]["timestamp"]

    await mediation_service.add_message(DISPUTE_ID, TENANT_SESSION, "Follow-up")

    filtered = await mediation_service.get_messages(DISPUTE_ID, since_timestamp)
    assert len(filtered) >= 1
    assert all(message["timestamp"] > since_timestamp for message in filtered)


@pytest.mark.asyncio
async def test_escalate_mediation(mediation_service):
    await _start(mediation_service)
    result = await mediation_service.escalate(DISPUTE_ID)

    assert result["mediation_status"] == "escalated"
    assert mediation_service._mediations[DISPUTE_ID].status.value == "escalated"


@pytest.mark.asyncio
async def test_cannot_start_mediation_twice(mediation_service):
    with patch(
        "llm_orchestrator.models.dispute.DisputeCase.start_mediation",
        side_effect=[None, ValueError("Mediation already active")],
    ):
        await _start(mediation_service)

        with pytest.raises(ValueError, match="already active"):
            await _start(mediation_service)


@pytest.mark.asyncio
async def test_cannot_send_message_after_settled(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)
    await mediation_service.respond_to_offer(
        DISPUTE_ID,
        LANDLORD_SESSION,
        offer.id,
        "accept",
    )

    with pytest.raises(ValueError, match="Mediation must be active"):
        await mediation_service.add_message(DISPUTE_ID, TENANT_SESSION, "Too late")


@pytest.mark.asyncio
async def test_cannot_accept_own_offer(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)

    with pytest.raises(ValueError, match="opposite party"):
        await mediation_service.respond_to_offer(
            DISPUTE_ID,
            TENANT_SESSION,
            offer.id,
            "accept",
        )


@pytest.mark.asyncio
async def test_get_settlement_after_settle(mediation_service):
    await _start(mediation_service)
    offer = await mediation_service.submit_offer(DISPUTE_ID, TENANT_SESSION, 500)
    await mediation_service.respond_to_offer(
        DISPUTE_ID,
        LANDLORD_SESSION,
        offer.id,
        "accept",
    )

    settlement = await mediation_service.get_settlement(DISPUTE_ID)

    assert settlement["status"] == "settled"
    assert settlement["settlement_amount"] == 500


@pytest.mark.asyncio
async def test_reasoning_trace_round_trips_through_session_json(mediation_service):
    """Start mediation, confirm the opener's trace survives save + reload from disk."""
    from llm_orchestrator.models.mediation import MediationSession

    await _start(mediation_service)

    session = mediation_service._mediations[DISPUTE_ID]
    opener = next(m for m in session.messages if m.sender_role == "ai_mediator")
    # The deterministic fallback does not call tools, so the trace has no
    # tool_call steps — but it DOES have a model_turn step and a terminated
    # summary. That's enough to exercise the persistence round-trip.
    assert opener.reasoning_trace is not None
    assert len(opener.reasoning_trace.steps) >= 1

    # Force a save then rehydrate the session from disk.
    mediation_service._save_session(session)
    mediation_path = mediation_service.mediations_dir / f"mediation_{DISPUTE_ID}.json"
    with open(mediation_path) as f:
        data = json.load(f)
    reloaded = MediationSession.model_validate(data)

    reloaded_opener = next(
        m for m in reloaded.messages if m.sender_role == "ai_mediator"
    )
    assert reloaded_opener.reasoning_trace is not None
    assert reloaded_opener.reasoning_trace.model_dump(mode="json") == (
        opener.reasoning_trace.model_dump(mode="json")
    )
