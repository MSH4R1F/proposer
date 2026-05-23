"""Domain catalog router — read-only view of the domain registry for the UI."""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel
import structlog

from apps.api.src.config import config
from apps.api.src.domain_runtime import resolve_domain_runtime
from domain_core.registry import list_domain_specs
from domain_core.spec import DomainSpec

logger = structlog.get_logger()
router = APIRouter(prefix="/domains", tags=["domains"])


class PartyRoleOption(BaseModel):
    value: str
    label: str
    blurb: str = ""


class DomainCatalogItem(BaseModel):
    id: str
    user_facing_name: str
    family: str
    stage: str
    availability: str  # live | research_beta | coming_soon
    party_roles: List[PartyRoleOption]
    intake_modes: List[str]
    matter_types: List[str]
    disclaimer_level: str  # standard | research


def _party_options(spec: DomainSpec) -> List[PartyRoleOption]:
    out: List[PartyRoleOption] = []
    for role in spec.party_roles:
        meta = spec.party_role_labels.get(role)
        if meta:
            out.append(
                PartyRoleOption(
                    value=role,
                    label=meta.get("label", role),
                    blurb=meta.get("blurb", ""),
                )
            )
    return out


def _availability(domain_id: str) -> str:
    """Compute UI availability from the real launch gate.

    A domain is ``live`` only if it actually resolves usable on the
    user-facing (``production``-mode) request path. Research/beta-staged
    domains fail closed there, so they surface as ``coming_soon`` until their
    launch gate passes — honoring the project's fail-closed policy. The
    ``research_beta`` value remains valid for a future beta-staged domain
    that is genuinely user-runnable, but is not produced today.
    """
    try:
        runtime = resolve_domain_runtime(domain_id, requested_mode="production")
    except Exception:  # noqa: BLE001 — unknown/unregistered -> not selectable
        return "coming_soon"
    return "live" if runtime.is_usable else "coming_soon"


def _to_item(spec: DomainSpec) -> DomainCatalogItem:
    domain_id = str(spec.id)
    availability = _availability(domain_id)
    intake_modes = ["guided", "bulk"] if domain_id == config.default_domain else ["bulk"]
    return DomainCatalogItem(
        id=domain_id,
        user_facing_name=spec.user_facing_name,
        family=spec.family.value,
        stage=spec.stage.value,
        availability=availability,
        party_roles=_party_options(spec),
        intake_modes=intake_modes,
        matter_types=list(spec.matter_types),
        disclaimer_level="standard" if availability == "live" else "research",
    )


@router.get("", response_model=List[DomainCatalogItem])
@router.get("/", response_model=List[DomainCatalogItem])
async def list_domains() -> List[DomainCatalogItem]:
    specs = list_domain_specs()
    items = [_to_item(s) for s in specs]
    rank = {"live": 0, "research_beta": 1, "coming_soon": 2}
    items.sort(key=lambda i: (rank[i.availability], i.user_facing_name))
    logger.debug("domains_listed", count=len(items))
    return items
