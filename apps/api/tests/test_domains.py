import pytest


@pytest.mark.asyncio
async def test_domains_lists_all_registered(async_client):
    resp = await async_client.get("/domains")
    assert resp.status_code == 200
    items = resp.json()
    ids = {d["id"] for d in items}
    assert "housing.deposit.v1" in ids
    assert "employment.unfair_dismissal.v1" in ids
    assert len(items) >= 5


@pytest.mark.asyncio
async def test_deposit_is_live_with_guided_and_bulk(async_client):
    items = (await async_client.get("/domains")).json()
    deposit = next(d for d in items if d["id"] == "housing.deposit.v1")
    assert deposit["availability"] == "live"
    assert deposit["disclaimer_level"] == "standard"
    assert set(deposit["intake_modes"]) == {"guided", "bulk"}
    roles = {r["value"]: r["label"] for r in deposit["party_roles"]}
    assert roles["tenant"] == "Tenant" and roles["landlord"] == "Landlord"
    assert "letting_agent" not in roles


@pytest.mark.asyncio
async def test_non_default_domain_has_research_disclaimer_and_bulk_only(async_client):
    items = (await async_client.get("/domains")).json()
    emp = next(d for d in items if d["id"] == "employment.unfair_dismissal.v1")
    assert emp["availability"] in {"research_beta", "coming_soon"}
    if emp["availability"] != "live":
        assert emp["disclaimer_level"] == "research"
    assert emp["intake_modes"] == ["bulk"]


@pytest.mark.asyncio
async def test_chat_start_rejects_role_not_in_domain(async_client):
    # 'claimant' is not a deposit party_role -> 400
    resp = await async_client.post("/chat/start", json={"role": "claimant", "domain_id": "housing.deposit.v1"})
    assert resp.status_code == 400
