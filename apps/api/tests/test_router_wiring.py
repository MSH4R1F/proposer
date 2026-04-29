"""Smoke test that every router imports its service factory through dependencies.

Phase 5.4 wired all six routers to construct services through
``apps.api.src.dependencies.get_*_service`` rather than importing the
legacy singleton getter directly. The factories accept ``Depends(get_uow)``
so Phase 6-9 service rewrites can swap in UoW-aware constructors without
further router edits. This test fails fast if a router regresses to the
legacy import path.
"""

from __future__ import annotations

import importlib

import pytest

ROUTER_FACTORIES = {
    "apps.api.src.routers.chat": ("get_intake_service", "get_dispute_service"),
    "apps.api.src.routers.cases": ("get_intake_service",),
    "apps.api.src.routers.disputes": ("get_dispute_service",),
    "apps.api.src.routers.predictions": ("get_prediction_service",),
    "apps.api.src.routers.evidence": ("get_storage_service",),
    "apps.api.src.routers.mediation": ("get_mediation_service",),
}


@pytest.mark.parametrize("router_module,factory_names", ROUTER_FACTORIES.items())
def test_router_uses_dependencies_factory(router_module: str, factory_names: tuple[str, ...]) -> None:
    deps = importlib.import_module("apps.api.src.dependencies")
    router = importlib.import_module(router_module)
    for name in factory_names:
        assert getattr(router, name) is getattr(deps, name), (
            f"{router_module}.{name} must come from apps.api.src.dependencies "
            f"(Phase 5.4 router wiring), not the legacy service module."
        )
