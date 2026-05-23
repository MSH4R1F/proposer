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
async def test_research_staged_domains_are_coming_soon(async_client):
    # Research-staged domains fail closed on the production request path,
    # so the catalog must surface them as coming_soon (not selectable) until
    # their launch gate passes. They are still listed (visible, disabled).
    items = (await async_client.get("/domains")).json()
    for did in [
        "employment.unfair_dismissal.v1",
        "housing.property_chamber.rro.v1",
        "housing.rent_determination.v1",
        "housing.repairs_social.v1",
    ]:
        d = next(x for x in items if x["id"] == did)
        assert d["availability"] == "coming_soon", f"{did} should be coming_soon"
        assert d["intake_modes"] == ["bulk"]


@pytest.mark.asyncio
async def test_chat_start_rejects_role_not_in_domain(async_client):
    # 'claimant' is not a deposit party_role -> 400
    resp = await async_client.post("/chat/start", json={"role": "claimant", "domain_id": "housing.deposit.v1"})
    assert resp.status_code == 400
