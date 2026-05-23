# Domain-Agnostic Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend present and run any backend-configured legal domain (not just housing deposit / tenant-landlord), via an explicit domain picker driven by a new backend domain catalog.

**Architecture:** Backend gains a read-only `GET /domains` catalog (serializing the existing domain registry) and a `party_role_labels` field on each domain spec. The frontend fetches the catalog, shows a picker as the first step, holds the selected domain in a `DomainContext`, and drives party-role buttons, copy, intake mode, and prediction/mediation framing from it. Deposit keeps guided+bulk intake; other domains use bulk paste only. Backend domain specs remain the single source of truth.

**Tech Stack:** FastAPI + Pydantic + `domain_core` registry (backend, Python 3.9, shared venv at repo root); Next.js 15 App Router + React + TypeScript + Tailwind (frontend). Backend tests: pytest via `make test-api`. Frontend verification: `npm run type-check` + Claude-in-Chrome browser E2E (no unit-test framework present).

**Spec:** `docs/superpowers/specs/2026-05-22-domain-agnostic-frontend-design.md`

**Conventions used throughout:**
- `VENV=/Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv`
- Backend run from worktree root with `$VENV/bin/python scripts/api.py`; tests with `$VENV/bin/python -m pytest`.
- The worktree must have `data/embeddings` + `data/indices` symlinked to the main repo (see memory: worktree-corpus-setup) before any prediction/mediation E2E.
- Party-role canonical values per domain: deposit `[tenant, landlord, letting_agent]`; rro `[tenant, landlord]`; rent_determination `[tenant, landlord]`; repairs_social `[resident, landlord_provider]`; employment `[claimant, respondent_employer]`.

---

## File Structure

**Backend (create):**
- `apps/api/src/routers/domains.py` — `GET /domains` catalog endpoint + response models.
- `apps/api/tests/test_domains.py` — endpoint tests.

**Backend (modify):**
- `packages/domain_core/spec.py` — add `party_role_labels` field to `DomainSpec`.
- `packages/domain_core/domains/*.yaml` (5 files) — add `party_role_labels` blocks.
- `apps/api/src/main.py` — register the domains router.
- `apps/api/src/routers/chat.py` — validate `role` against the resolved domain's `party_roles`.
- `.env` (main repo root) — expand `ENABLED_DOMAINS`.

**Frontend (create):**
- `apps/web/lib/api/domains.ts` — catalog client.
- `apps/web/lib/contexts/DomainContext.tsx` — provider + `useDomain()` hook.
- `apps/web/components/chat/DomainPicker.tsx` — picker UI.
- `apps/web/components/shared/ResearchBetaBanner.tsx` — disclaimer banner.

**Frontend (modify):**
- `apps/web/lib/types/domain.ts` — add catalog types.
- `apps/web/lib/types/chat.ts` — widen `PartyRole` to `string`.
- `apps/web/lib/api/chat.ts` + `apps/web/lib/hooks/useChat.ts` — thread `domain_id`.
- `apps/web/components/chat/ChatContainer.tsx` — slot picker before role; route intake by domain.
- `apps/web/components/chat/RoleSelector.tsx` — render from domain party-role labels.
- `apps/web/components/chat/DisputeEntrySelector.tsx`, `MessageList.tsx`, `app/layout.tsx`, `components/shared/Footer.tsx`, `components/chat/InviteCodeDisplay.tsx` — domain-driven/neutral copy.
- `apps/web/components/prediction/OutcomeDisplay.tsx`, `IssuePredictionCard.tsx`, `components/mediation/ExpectationCard.tsx` — positional role framing.
- `apps/web/app/providers.tsx` — wrap with `DomainProvider`.

---

## Phase A — Backend domain catalog + labels

### Task 1: Add `party_role_labels` to DomainSpec + populate YAMLs

**Files:**
- Modify: `packages/domain_core/spec.py` (DomainSpec, ~line 251)
- Modify: `packages/domain_core/domains/housing_deposit_v1.yaml`, `employment_unfair_dismissal_v1.yaml`, `housing_property_chamber_rro_v1.yaml`, `housing_rent_determination_v1.yaml`, `housing_repairs_social_v1.yaml`
- Test: `packages/domain_core/tests/test_party_role_labels.py` (create)

- [ ] **Step 1: Write the failing test**

Create `packages/domain_core/tests/test_party_role_labels.py`:
```python
from domain_core.registry import get_domain_spec


def test_deposit_has_party_role_labels():
    spec = get_domain_spec("housing.deposit.v1")
    assert spec.party_role_labels["tenant"]["label"] == "Tenant"
    assert spec.party_role_labels["landlord"]["label"] == "Landlord"


def test_employment_labels_humanise_machine_roles():
    spec = get_domain_spec("employment.unfair_dismissal.v1")
    assert spec.party_role_labels["claimant"]["label"] == "Employee (claimant)"
    assert spec.party_role_labels["respondent_employer"]["label"] == "Employer (respondent)"


def test_every_labelled_role_is_a_real_party_role():
    for did in [
        "housing.deposit.v1", "housing.property_chamber.rro.v1",
        "housing.rent_determination.v1", "housing.repairs_social.v1",
        "employment.unfair_dismissal.v1",
    ]:
        spec = get_domain_spec(did)
        assert spec.party_role_labels, f"{did} missing party_role_labels"
        for role in spec.party_role_labels:
            assert role in spec.party_roles, f"{did}: {role} not in party_roles"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd <worktree> && PYTHONPATH=packages $VENV/bin/python -m pytest packages/domain_core/tests/test_party_role_labels.py -v`
Expected: FAIL — `AttributeError`/validation error: `DomainSpec` has no `party_role_labels` (and `extra="forbid"` rejects it in YAML).

- [ ] **Step 3: Add the field to DomainSpec**

In `packages/domain_core/spec.py`, inside `class DomainSpec(BaseModel)`, immediately after the line `party_roles: List[str]` add:
```python
    party_role_labels: Dict[str, Dict[str, str]] = Field(default_factory=dict)
```
Ensure `Dict` is imported (`from typing import Dict` — it almost certainly already is; add if missing).

- [ ] **Step 4: Add `party_role_labels` to each domain YAML**

In each YAML, directly under the existing `party_roles:` block, add a `party_role_labels:` block. Only label the *selectable adversarial* roles (omit `letting_agent`).

`housing_deposit_v1.yaml`:
```yaml
party_role_labels:
  tenant: { label: "Tenant", blurb: "Disputing deposit deductions" }
  landlord: { label: "Landlord", blurb: "Seeking deposit recovery" }
```
`housing_property_chamber_rro_v1.yaml`:
```yaml
party_role_labels:
  tenant: { label: "Tenant", blurb: "Applying for a rent repayment order" }
  landlord: { label: "Landlord", blurb: "Responding to the application" }
```
`housing_rent_determination_v1.yaml`:
```yaml
party_role_labels:
  tenant: { label: "Tenant", blurb: "Challenging the rent" }
  landlord: { label: "Landlord", blurb: "Defending the rent" }
```
`housing_repairs_social_v1.yaml`:
```yaml
party_role_labels:
  resident: { label: "Resident", blurb: "Reporting disrepair or a complaint" }
  landlord_provider: { label: "Housing provider", blurb: "Responding to the complaint" }
```
`employment_unfair_dismissal_v1.yaml`:
```yaml
party_role_labels:
  claimant: { label: "Employee (claimant)", blurb: "Bringing the claim" }
  respondent_employer: { label: "Employer (respondent)", blurb: "Responding to the claim" }
```

- [ ] **Step 5: Run the test to confirm it passes**

Run: `PYTHONPATH=packages $VENV/bin/python -m pytest packages/domain_core/tests/test_party_role_labels.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**
```bash
git add packages/domain_core/spec.py packages/domain_core/domains/*.yaml packages/domain_core/tests/test_party_role_labels.py
git commit -m "feat(domain_core): add party_role_labels to domain specs"
```

---

### Task 2: `GET /domains` catalog endpoint

**Files:**
- Create: `apps/api/src/routers/domains.py`
- Create: `apps/api/tests/test_domains.py`
- Modify: `apps/api/src/main.py` (router import line 26; registration ~line 124)

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_domains.py`:
```python
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
    assert "letting_agent" not in roles  # only labelled roles are surfaced


@pytest.mark.asyncio
async def test_non_enabled_domain_is_coming_soon(async_client):
    # conftest leaves ENABLED_DOMAINS at its default (deposit only) unless overridden.
    items = (await async_client.get("/domains")).json()
    emp = next(d for d in items if d["id"] == "employment.unfair_dismissal.v1")
    assert emp["availability"] in {"research_beta", "coming_soon"}
    if emp["availability"] != "live":
        assert emp["disclaimer_level"] == "research"
    assert emp["intake_modes"] == ["bulk"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd <worktree> && make test-api` (or the explicit command below)
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $VENV/bin/python -m pytest apps/api/tests/test_domains.py -p pytest_asyncio.plugin -p no:cacheprovider -v`
Expected: FAIL — 404 (no `/domains` route).

- [ ] **Step 3: Create the router**

Create `apps/api/src/routers/domains.py`:
```python
"""Domain catalog router — read-only view of the domain registry for the UI."""

from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
import structlog

from apps.api.src.config import config
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
    availability: str  # "live" | "research_beta" | "coming_soon"
    party_roles: List[PartyRoleOption]
    intake_modes: List[str]
    matter_types: List[str]
    disclaimer_level: str  # "standard" | "research"


def _party_options(spec: DomainSpec) -> List[PartyRoleOption]:
    # Only surface roles that have a label (the selectable adversarial parties).
    out: List[PartyRoleOption] = []
    for role in spec.party_roles:
        meta = spec.party_role_labels.get(role)
        if meta:
            out.append(PartyRoleOption(value=role, label=meta.get("label", role),
                                       blurb=meta.get("blurb", "")))
    return out


def _availability(domain_id: str) -> str:
    if domain_id == config.default_domain:
        return "live"
    if domain_id in config.enabled_domains:
        return "research_beta"
    return "coming_soon"


def _to_item(spec: DomainSpec) -> DomainCatalogItem:
    domain_id = str(spec.id)
    availability = _availability(domain_id)
    intake_modes = ["guided", "bulk"] if domain_id == config.default_domain else ["bulk"]
    return DomainCatalogItem(
        id=domain_id,
        user_facing_name=spec.user_facing_name,
        family=str(spec.family),
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
    """Return all registered domains with UI-facing metadata + computed availability."""
    specs = list_domain_specs()
    items = [_to_item(s) for s in specs]
    # Order: live first, then research_beta, then coming_soon; alpha within group.
    rank = {"live": 0, "research_beta": 1, "coming_soon": 2}
    items.sort(key=lambda i: (rank[i.availability], i.user_facing_name))
    logger.debug("domains_listed", count=len(items))
    return items
```
Note: confirm the import name for the global config. `apps/api/src/config.py` exposes a module-level `config` instance (used by `domain_runtime`/routers); if the symbol differs, import the existing instance the other routers use (grep `from apps.api.src.config import`).

- [ ] **Step 4: Register the router in main.py**

In `apps/api/src/main.py` line 26 change:
```python
from apps.api.src.routers import chat, evidence, predictions, cases, disputes, mediation
```
to:
```python
from apps.api.src.routers import chat, evidence, predictions, cases, disputes, mediation, domains
```
And in the registration block (after `app.include_router(mediation.router)`, ~line 124) add:
```python
    app.include_router(domains.router)
```
Add `"domains"` to the `routers=[...]` debug log list on line ~117.

- [ ] **Step 5: Run the test to confirm it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $VENV/bin/python -m pytest apps/api/tests/test_domains.py -p pytest_asyncio.plugin -p no:cacheprovider -v`
Expected: PASS (3 tests). If `test_non_enabled_domain_is_coming_soon` shows `research_beta`, that's fine — conftest may enable more; the assertion allows both.

- [ ] **Step 6: Commit**
```bash
git add apps/api/src/routers/domains.py apps/api/tests/test_domains.py apps/api/src/main.py
git commit -m "feat(api): add GET /domains catalog endpoint"
```

---

### Task 3: Validate `role` against the resolved domain's party_roles

**Files:**
- Modify: `apps/api/src/routers/chat.py` (the `start_session` handler; current check `if request.role not in ("tenant", "landlord")` ~line 294)
- Test: add to `apps/api/tests/test_domains.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_domains.py`:
```python
@pytest.mark.asyncio
async def test_chat_start_rejects_role_not_in_domain(async_client):
    # 'claimant' is not a deposit party_role -> 400
    resp = await async_client.post("/chat/start", json={"role": "claimant", "domain_id": "housing.deposit.v1"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $VENV/bin/python -m pytest apps/api/tests/test_domains.py::test_chat_start_rejects_role_not_in_domain -p pytest_asyncio.plugin -p no:cacheprovider -v`
Expected: FAIL — currently returns 200/other because the check only compares against the literal `("tenant","landlord")` and `claimant` would fall through differently; confirm the actual current behavior in the failure output.

- [ ] **Step 3: Replace the hardcoded role check**

In `apps/api/src/routers/chat.py` `start_session`, after the domain is resolved (`runtime = _resolve_domain_or_400(request.domain_id)`), replace the hardcoded validation:
```python
    if request.role not in ("tenant", "landlord"):
        raise HTTPException(status_code=400, detail="role must be tenant or landlord")
```
with:
```python
    allowed_roles = runtime.domain_spec.party_roles
    if request.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"role must be one of {allowed_roles} for domain {runtime.domain_id}",
        )
```
(If the resolve call happens after the role check today, move the role check below the resolve call. Apply the same change to `bulk_intake` if it has an identical hardcoded check.)

- [ ] **Step 4: Run the test to confirm it passes**

Run: same as Step 2. Expected: PASS. Then run the full chat suite to confirm no regression: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $VENV/bin/python -m pytest apps/api/tests/test_chat*.py apps/api/tests/test_domains.py -p pytest_asyncio.plugin -p no:cacheprovider -v`

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/routers/chat.py apps/api/tests/test_domains.py
git commit -m "fix(api): validate intake role against domain party_roles"
```

---

### Task 4: Enable the research domains (config)

**Files:** Modify `.env` (main repo root: `/Users/msharif/Documents/Projects/proposer/legal-mediation-system/.env`)

- [ ] **Step 1: Expand ENABLED_DOMAINS**

Change `ENABLED_DOMAINS=housing.deposit.v1` to:
```
ENABLED_DOMAINS=housing.deposit.v1,employment.unfair_dismissal.v1,housing.property_chamber.rro.v1,housing.rent_determination.v1,housing.repairs_social.v1
```
Keep `DEFAULT_DOMAIN=housing.deposit.v1` and `DOMAIN_STRICT_EVAL_GATES=false`.

- [ ] **Step 2: Restart backend and verify the catalog**

Run (restart): `pkill -f scripts/api.py; $VENV/bin/python scripts/api.py &` then
`curl -s localhost:8000/domains | python3 -m json.tool`
Expected: 5 items; deposit `availability:"live"`, the other four `availability:"research_beta"`, each with `intake_modes:["bulk"]` and `disclaimer_level:"research"`.

- [ ] **Step 3: Per-domain runnability gate (verify, then keep or demote)**

For each non-deposit domain, smoke-test bulk-intake + prediction against its seed corpus:
```bash
curl -s -X POST localhost:8000/chat/bulk-intake -H 'Content-Type: application/json' \
  -d '{"role":"claimant","case_text":"<short representative case>","domain_id":"employment.unfair_dismissal.v1","create_dispute":false}'
```
Then `POST /predictions/generate` with the returned `case_id`. If a domain 500s or returns `total_cases_analyzed=0` (no usable prompt pack/corpus), REMOVE it from `ENABLED_DOMAINS` so the catalog marks it `coming_soon`. Record which domains passed.

- [ ] **Step 4: Commit (the .env is gitignored; commit a note in the design log instead)**

`.env` is gitignored — do not commit it. Instead append the verified-domain list to `docs/scraping-runs.md` or the plan's execution notes. No code commit for this task.

---

## Phase B — Frontend catalog client + context

### Task 5: Catalog types + client

**Files:**
- Modify: `apps/web/lib/types/domain.ts` (append types)
- Create: `apps/web/lib/api/domains.ts`

- [ ] **Step 1: Add catalog types**

Append to `apps/web/lib/types/domain.ts`:
```typescript
export type DomainAvailability = 'live' | 'research_beta' | 'coming_soon';

export interface PartyRoleOption {
  value: string;
  label: string;
  blurb?: string;
}

export interface DomainCatalogItem {
  id: string;
  user_facing_name: string;
  family: string;
  stage: string;
  availability: DomainAvailability;
  party_roles: PartyRoleOption[];
  intake_modes: ('guided' | 'bulk')[];
  matter_types: string[];
  disclaimer_level: 'standard' | 'research';
}
```

- [ ] **Step 2: Create the client**

Create `apps/web/lib/api/domains.ts`:
```typescript
import { api } from './client';
import type { DomainCatalogItem } from '@/lib/types/domain';

export const domainsApi = {
  list: () => api.get<DomainCatalogItem[]>('/domains'),
};
```

- [ ] **Step 3: Verify typecheck**

Run: `cd apps/web && npm run type-check`
Expected: no new errors.

- [ ] **Step 4: Commit**
```bash
git add apps/web/lib/types/domain.ts apps/web/lib/api/domains.ts
git commit -m "feat(web): domain catalog types + client"
```

---

### Task 6: DomainContext + provider

**Files:**
- Create: `apps/web/lib/contexts/DomainContext.tsx`
- Modify: `apps/web/app/providers.tsx`

- [ ] **Step 1: Create the context + provider**

Create `apps/web/lib/contexts/DomainContext.tsx`:
```typescript
'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import type { DomainCatalogItem } from '@/lib/types/domain';
import { domainsApi } from '@/lib/api/domains';

const STORAGE_KEY = 'proposer:selected-domain-id';

interface DomainContextValue {
  catalog: DomainCatalogItem[];
  loading: boolean;
  error: string | null;
  selected: DomainCatalogItem | null;
  selectDomain: (id: string) => void;
  clearDomain: () => void;
}

const DomainContext = createContext<DomainContextValue | null>(null);

export function DomainProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<DomainCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    domainsApi
      .list()
      .then((items) => setCatalog(items))
      .catch((e) => setError(e?.message ?? 'Failed to load domains'))
      .finally(() => setLoading(false));
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setSelectedId(saved);
    } catch {}
  }, []);

  const selectDomain = (id: string) => {
    setSelectedId(id);
    try { localStorage.setItem(STORAGE_KEY, id); } catch {}
  };
  const clearDomain = () => {
    setSelectedId(null);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  };

  const selected = catalog.find((d) => d.id === selectedId) ?? null;

  return (
    <DomainContext.Provider
      value={{ catalog, loading, error, selected, selectDomain, clearDomain }}
    >
      {children}
    </DomainContext.Provider>
  );
}

export function useDomain(): DomainContextValue {
  const ctx = useContext(DomainContext);
  if (!ctx) throw new Error('useDomain must be used within DomainProvider');
  return ctx;
}
```

- [ ] **Step 2: Wrap the app**

Replace `apps/web/app/providers.tsx` body:
```typescript
'use client';

import { ReactNode } from 'react';
import { DomainProvider } from '@/lib/contexts/DomainContext';

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return <DomainProvider>{children}</DomainProvider>;
}
```

- [ ] **Step 3: Verify typecheck + app boot**

Run: `cd apps/web && npm run type-check`. Then load `http://localhost:3000/` in the browser — it should render unchanged (provider is transparent). Check console for no errors.

- [ ] **Step 4: Commit**
```bash
git add apps/web/lib/contexts/DomainContext.tsx apps/web/app/providers.tsx
git commit -m "feat(web): DomainContext provider + useDomain hook"
```

---

## Phase C — Picker + flow + threading

### Task 7: DomainPicker component

**Files:** Create `apps/web/components/chat/DomainPicker.tsx`

- [ ] **Step 1: Create the component**

Create `apps/web/components/chat/DomainPicker.tsx`:
```typescript
'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDomain } from '@/lib/contexts/DomainContext';

interface DomainPickerProps {
  onSelect: (domainId: string) => void;
}

export function DomainPicker({ onSelect }: DomainPickerProps) {
  const { catalog, loading, error } = useDomain();

  if (loading) {
    return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading domains…</div>;
  }
  if (error) {
    return <div className="text-destructive text-sm">Couldn’t load domains: {error}</div>;
  }

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">What kind of dispute is this?</h1>
        <p className="text-muted-foreground">Choose the area that best matches your situation.</p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {catalog.map((d) => {
          const disabled = d.availability === 'coming_soon';
          return (
            <button
              key={d.id}
              onClick={() => !disabled && onSelect(d.id)}
              disabled={disabled}
              className={cn(
                'group text-left rounded-xl border-2 border-border/50 p-4 transition-all',
                'hover:border-primary/30 hover:bg-muted/50',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'focus:outline-none focus:ring-2 focus:ring-primary/20'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">{d.user_facing_name}</span>
                {d.availability === 'research_beta' && <Badge variant="secondary">Research / beta</Badge>}
                {d.availability === 'coming_soon' && <Badge variant="outline">Coming soon</Badge>}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {d.party_roles.map((r) => r.label).join(' vs ')}
              </p>
              {!disabled && <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-2" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```
(If `Badge` isn't already in `components/ui/`, reuse the variant component used elsewhere — grep for `from '@/components/ui/badge'`; it is imported by `ExpectationCard.tsx`, so it exists.)

- [ ] **Step 2: Verify typecheck**

Run: `cd apps/web && npm run type-check`. Expected: no new errors.

- [ ] **Step 3: Commit**
```bash
git add apps/web/components/chat/DomainPicker.tsx
git commit -m "feat(web): domain picker component"
```

---

### Task 8: Slot picker into ChatContainer; widen PartyRole

**Files:**
- Modify: `apps/web/lib/types/chat.ts` (PartyRole)
- Modify: `apps/web/components/chat/ChatContainer.tsx`

- [ ] **Step 1: Widen PartyRole**

In `apps/web/lib/types/chat.ts` change:
```typescript
export type PartyRole = 'tenant' | 'landlord';
```
to:
```typescript
// Domain-driven: the concrete values come from the selected domain's party_roles.
export type PartyRole = string;
```

- [ ] **Step 2: Add domain step to ChatContainer state + flow**

In `apps/web/components/chat/ChatContainer.tsx`:
- Import: `import { useDomain } from '@/lib/contexts/DomainContext';` and `import { DomainPicker } from './DomainPicker';`
- Inside the component, add: `const { selected: selectedDomain, selectDomain } = useDomain();`
- After the `entryMode`/`selectedRole` state declarations, the flow gains a domain step. Update the step booleans (around lines 179–185) so domain selection precedes role selection for the "new dispute" path:
```typescript
  const noActiveSession = !sessionId && !currentSessionId;
  const showEntrySelector = noActiveSession && entryMode === 'select' && !selectedRole;
  const needDomain = noActiveSession && entryMode === 'new' && !selectedDomain;
  const showDomainPicker = needDomain;
  const showRoleSelectorForNew = noActiveSession && entryMode === 'new' && selectedDomain && !selectedRole;
  const showRoleSelectorForJoin = noActiveSession && entryMode === 'join' && pendingInviteCode && !selectedRole;
  const showIntakeModeSelector = noActiveSession && selectedRole && intakeMode === 'select';
  const showBulkPasteForm = noActiveSession && selectedRole && intakeMode === 'paste';
```
- In the JSX, add a branch BEFORE the role-selector branch:
```tsx
) : showDomainPicker ? (
  <div className="flex-1 flex flex-col items-center justify-center p-8">
    <DomainPicker onSelect={(id) => selectDomain(id)} />
  </div>
```
- The role-selector-for-new heading/copy now reads from the domain (handled in Task 9 via RoleSelector props).

- [ ] **Step 3: Verify in browser**

Run the app. Flow: Landing → Start Your Case → "Start New Dispute" → **domain picker appears** → pick "Tenancy deposit dispute" → role selector. Pick "Unfair dismissal" (research-beta badge) → role selector. Screenshot each; confirm no console errors.

- [ ] **Step 4: Commit**
```bash
git add apps/web/lib/types/chat.ts apps/web/components/chat/ChatContainer.tsx
git commit -m "feat(web): domain picker step before role selection"
```

---

### Task 9: Render RoleSelector from domain party-role labels

**Files:** Modify `apps/web/components/chat/RoleSelector.tsx`; pass roles from `ChatContainer.tsx`.

- [ ] **Step 1: Make RoleSelector domain-driven**

Replace `apps/web/components/chat/RoleSelector.tsx` with:
```typescript
'use client';

import { Home, User, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PartyRoleOption } from '@/lib/types/domain';

interface RoleSelectorProps {
  roles: PartyRoleOption[];
  onSelect: (role: string) => void;
  disabled?: boolean;
}

export function RoleSelector({ roles, onSelect, disabled }: RoleSelectorProps) {
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="grid sm:grid-cols-2 gap-3">
        {roles.map((role, idx) => (
          <button
            key={role.value}
            onClick={() => onSelect(role.value)}
            disabled={disabled}
            className={cn(
              'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
              'bg-background hover:bg-muted/50 hover:border-primary/30 transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
            )}
          >
            <div className={cn('p-3 rounded-xl transition-transform group-hover:scale-110',
              idx === 0 ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                        : 'bg-amber-500/10 text-amber-600 dark:text-amber-400')}>
              {idx === 0 ? <User className="h-6 w-6" /> : <Home className="h-6 w-6" />}
            </div>
            <div className="flex-1 text-left">
              <span className="block font-semibold">I'm the {role.label}</span>
              {role.blurb && <span className="block text-xs text-muted-foreground">{role.blurb}</span>}
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Pass roles from ChatContainer**

In `ChatContainer.tsx`, every `<RoleSelector onSelect={handleRoleSelect} disabled={isLoading} />` becomes:
```tsx
<RoleSelector roles={selectedDomain?.party_roles ?? []} onSelect={handleRoleSelect} disabled={isLoading} />
```
The fallback welcome `showRoleSelector` branch (line ~300) should also guard on a domain being selected; if `selectedDomain` is null there, fall back to deposit by selecting `housing.deposit.v1` (call `selectDomain('housing.deposit.v1')`) so resumed/legacy sessions still work.

- [ ] **Step 3: Verify in browser**

Deposit → role selector shows "I'm the Tenant" / "I'm the Landlord". Employment → "I'm the Employee (claimant)" / "I'm the Employer (respondent)". No console errors.

- [ ] **Step 4: Commit**
```bash
git add apps/web/components/chat/RoleSelector.tsx apps/web/components/chat/ChatContainer.tsx
git commit -m "feat(web): render role selector from domain party-role labels"
```

---

### Task 10: Thread domain_id through the chat API

**Files:** Modify `apps/web/lib/api/chat.ts`, `apps/web/lib/hooks/useChat.ts`, `apps/web/components/chat/ChatContainer.tsx`.

- [ ] **Step 1: Add domain_id to API calls**

In `apps/web/lib/api/chat.ts`, extend the options on `startSession` and `bulkIntake`:
```typescript
  startSession: (role: PartyRole, options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }) =>
    api.post<StartSessionResponse>('/chat/start', {
      role,
      invite_code: options?.inviteCode,
      create_dispute: options?.createDispute ?? true,
      domain_id: options?.domainId,
    }),
```
and:
```typescript
  bulkIntake: (role: PartyRole, caseText: string, options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }) =>
    api.post<BulkIntakeResponse>('/chat/bulk-intake', {
      role,
      case_text: caseText,
      invite_code: options?.inviteCode,
      create_dispute: options?.createDispute ?? true,
      domain_id: options?.domainId,
    }),
```

- [ ] **Step 2: Pass domainId from useChat**

In `apps/web/lib/hooks/useChat.ts`, widen the `options` types on `startSession` and `startBulkSession` to include `domainId?: string` and forward it to `chatApi.startSession`/`chatApi.bulkIntake` (they already spread `options`, so just widen the type signatures).

- [ ] **Step 3: Supply domainId at call sites in ChatContainer**

Where `ChatContainer` calls `startSession(...)` / `startBulkSession(...)` (in `handleRoleSelect`/`handleBulkSubmit`), add `domainId: selectedDomain?.id` to the options object.

- [ ] **Step 4: Verify in browser + network**

Run the app, start a deposit case, and inspect the `/chat/start` (or `/chat/bulk-intake`) request body in the browser network panel — it must include `"domain_id":"housing.deposit.v1"`. Then an employment case must send `"domain_id":"employment.unfair_dismissal.v1"`.

- [ ] **Step 5: Commit**
```bash
git add apps/web/lib/api/chat.ts apps/web/lib/hooks/useChat.ts apps/web/components/chat/ChatContainer.tsx
git commit -m "feat(web): thread domain_id through chat intake calls"
```

---

### Task 11: Route non-deposit domains to bulk intake

**Files:** Modify `apps/web/components/chat/ChatContainer.tsx`.

- [ ] **Step 1: Skip the mode selector when guided isn't supported**

In `ChatContainer.tsx`, when a role is selected, decide intake mode by domain:
```typescript
  const supportsGuided = selectedDomain?.intake_modes.includes('guided') ?? true;
```
After `handleRoleSelect` sets the role, if `!supportsGuided` set `intakeMode` to `'paste'` directly (skip the selector). Update the step booleans:
```typescript
  const showIntakeModeSelector = noActiveSession && selectedRole && intakeMode === 'select' && supportsGuided;
  const showBulkPasteForm = noActiveSession && selectedRole && (intakeMode === 'paste' || (!supportsGuided && intakeMode !== 'guided'));
```

- [ ] **Step 2: Hide deposit-specific guided sidebar for non-deposit active sessions**

In the active-session branch, only render the deposit-shaped `IntakeSidebar` when `supportsGuided`; otherwise render the message list full-width (bulk sessions don't have the staged sidebar data).

- [ ] **Step 3: Verify in browser**

Employment: pick → role → goes straight to the paste form (no Guided/Paste choice). Paste a short unfair-dismissal case → submit → active session renders without the deposit sidebar → "Get Prediction" available. Deposit: still shows the Guided/Paste choice.

- [ ] **Step 4: Commit**
```bash
git add apps/web/components/chat/ChatContainer.tsx
git commit -m "feat(web): route non-deposit domains to bulk intake"
```

---

## Phase D — Copy + framing generalization

### Task 12: Domain-driven / neutral copy

**Files:** Modify `app/layout.tsx`, `components/chat/DisputeEntrySelector.tsx`, `components/chat/MessageList.tsx`, `components/shared/Footer.tsx`, `components/chat/InviteCodeDisplay.tsx`, `components/chat/ChatContainer.tsx` (fallback welcome copy).

- [ ] **Step 1: Neutralize global metadata**

`app/layout.tsx` metadata:
```typescript
export const metadata: Metadata = {
  title: 'Proposer - AI-Powered Dispute Resolution',
  description:
    'Predict likely legal outcomes and reach fair settlements, based on real tribunal and court decisions.',
  keywords: ['dispute resolution', 'UK legal', 'legal mediation', 'AI legal', 'tribunal outcomes'],
};
```

- [ ] **Step 2: Domain-driven entry/welcome copy**

`DisputeEntrySelector.tsx` subtitle "Get AI-powered guidance on your tenancy deposit dispute" → make it accept an optional `domainName?: string` prop and render `Get AI-powered guidance on your {domainName ?? 'legal'} matter`. Pass `selectedDomain?.user_facing_name` from `ChatContainer`. (Entry selector now shows AFTER domain pick for the new path; for the join path it can stay generic.)
`MessageList.tsx` line 33 hardcoded greeting and `ChatContainer.tsx` fallback welcome copy "tenancy deposit dispute" → "your {selectedDomain?.user_facing_name ?? 'dispute'}".

- [ ] **Step 3: Neutralize footer + invite copy**

`components/shared/Footer.tsx` "AI-Powered Deposit Dispute Resolution" → "AI-Powered Dispute Resolution".
`components/chat/InviteCodeDisplay.tsx` (and the duplicate in `IntakeSidebar.tsx`) share copy "Join My Deposit Dispute" → "Join My Dispute on Proposer".

- [ ] **Step 4: Verify in browser**

Tab title generic; deposit flow says "Tenancy deposit dispute"; employment flow says "Unfair dismissal". No console errors.

- [ ] **Step 5: Commit**
```bash
git add apps/web/app/layout.tsx apps/web/components/chat/DisputeEntrySelector.tsx apps/web/components/chat/MessageList.tsx apps/web/components/shared/Footer.tsx apps/web/components/chat/InviteCodeDisplay.tsx apps/web/components/chat/IntakeSidebar.tsx apps/web/components/chat/ChatContainer.tsx
git commit -m "feat(web): domain-driven and neutral copy"
```

---

### Task 13: Positional party framing in prediction/mediation

**Files:** Modify `components/prediction/OutcomeDisplay.tsx`, `components/prediction/IssuePredictionCard.tsx`, `components/mediation/ExpectationCard.tsx`.

- [ ] **Step 1: Map outcome to the domain's role labels**

These components currently say "Tenant Favored"/"Landlord Favored". Use `useDomain()` to get `selected?.party_roles` and map positionally: `party_roles[0]` ↔ the `tenant_*`/`tenant_wins` outcome, `party_roles[1]` ↔ `landlord_*`/`landlord_wins`. Concretely, in `OutcomeDisplay.tsx` derive the label:
```typescript
import { useDomain } from '@/lib/contexts/DomainContext';
// ...
const { selected } = useDomain();
const roleLabels = selected?.party_roles ?? [{ value: 'tenant', label: 'Tenant' }, { value: 'landlord', label: 'Landlord' }];
const favouredLabel = (outcome === 'tenant_wins' || outcome === 'tenant_win' || outcome === 'tenant_favored')
  ? `${roleLabels[0]?.label ?? 'First party'} Favoured`
  : (outcome === 'landlord_wins' || outcome === 'landlord_win' || outcome === 'landlord_favored')
    ? `${roleLabels[1]?.label ?? 'Second party'} Favoured`
    : config.label; // keep "Split Decision Likely" / "Outcome Uncertain"
```
Render `favouredLabel` instead of the static `config.label` for the win/favored cases (keep the existing gradient/icon mapping from the prior fix). Apply the same positional mapping in `IssuePredictionCard.tsx` (`isTenantFavored`/`isLandlordFavored` → role[0]/role[1]) and `ExpectationCard.tsx` (the `isTenant` framing and the `outcomeLabel` ternary).

- [ ] **Step 2: Verify in browser**

Employment prediction headline reads "Employee (claimant) Favoured" (not "Tenant Favoured"); deposit reads "Tenant Favoured" exactly as before (regression). Mediation expectation badge matches.

- [ ] **Step 3: Commit**
```bash
git add apps/web/components/prediction/OutcomeDisplay.tsx apps/web/components/prediction/IssuePredictionCard.tsx apps/web/components/mediation/ExpectationCard.tsx
git commit -m "feat(web): positional party-role framing in prediction & mediation"
```

---

## Phase E — Disclaimers + E2E

### Task 14: Research/beta disclaimer banner

**Files:** Create `apps/web/components/shared/ResearchBetaBanner.tsx`; render it on intake (`ChatContainer`), prediction page, and mediation pages when the active domain's `disclaimer_level === 'research'`.

- [ ] **Step 1: Create the banner**

Create `apps/web/components/shared/ResearchBetaBanner.tsx`:
```typescript
'use client';

import { AlertTriangle } from 'lucide-react';
import { useDomain } from '@/lib/contexts/DomainContext';

export function ResearchBetaBanner() {
  const { selected } = useDomain();
  if (!selected || selected.disclaimer_level !== 'research') return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
      <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
      <span>
        <strong>{selected.user_facing_name}</strong> is a research/beta domain. Predictions are
        experimental, based on a limited corpus, and must not be relied on. This is not legal advice.
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Mount it**

Render `<ResearchBetaBanner />` near the top of the chat intake area (`ChatContainer`), the prediction page (`app/prediction/[caseId]/page.tsx`, under the existing legal notice), and the mediation pages (`app/mediation/[disputeId]/layout.tsx` is a good single mount point).

- [ ] **Step 3: Verify in browser**

Employment intake/prediction/mediation show the amber banner; deposit shows none. No console errors.

- [ ] **Step 4: Commit**
```bash
git add apps/web/components/shared/ResearchBetaBanner.tsx apps/web/components/chat/ChatContainer.tsx apps/web/app/prediction/[caseId]/page.tsx apps/web/app/mediation/[disputeId]/layout.tsx
git commit -m "feat(web): research/beta disclaimer banner"
```

---

### Task 15: Full E2E verification + regression

**Files:** none (verification). Uses Claude-in-Chrome + the running stack with the corpus symlinked.

- [ ] **Step 1: Backend suite green**

Run: `cd <worktree> && make test-api`. Expected: all pass, including `test_domains.py` and `test_party_role_labels.py`.

- [ ] **Step 2: Typecheck + lint**

Run: `cd apps/web && npm run type-check && npm run lint`. Expected: no new errors.

- [ ] **Step 3: Deposit regression (browser)**

Landing → Start → domain picker → Tenancy deposit → Tenant → Guided → answer a few turns → prediction shows "Tenant Favoured" → Proceed to Mediation → expectation/offer flow. Confirms the existing flow is unchanged.

- [ ] **Step 4: Employment end-to-end (browser)**

Domain picker shows "Unfair dismissal" with a Research/beta badge → select → "I'm the Employee (claimant)" → goes straight to paste → paste a short unfair-dismissal case → submit → research banner visible → Get Prediction → headline frames as "Employee (claimant) Favoured" with citations → Proceed to Mediation → expectation renders. Capture screenshots.

- [ ] **Step 5: Coming-soon check**

Temporarily remove one domain from `ENABLED_DOMAINS`, restart, confirm the picker shows it disabled as "Coming soon" and it can't be selected. Restore config.

- [ ] **Step 6: Final commit (if any verification fixes were needed)**
```bash
git add -A
git commit -m "test(web): domain-agnostic E2E verification fixes"
```

---

## Self-Review notes (author)

- **Spec coverage:** catalog endpoint (Task 2), party_role_labels (Task 1), picker + context (Tasks 6–8), bulk routing for non-deposit (Task 11), positional framing (Task 13), readiness/disclaimers (Tasks 4, 14), deposit-unchanged (verified Task 15 Step 3). All spec sections mapped.
- **Risk: per-domain runnability** — Task 4 Step 3 verifies and demotes non-runnable domains to `coming_soon` via `ENABLED_DOMAINS`, exactly as the spec requires.
- **Known follow-up (out of scope):** backend outcome vocabulary stays housing-shaped; the frontend maps positionally (Task 13). Guided intake stays deposit-only (Task 11).
- **Type consistency:** `DomainCatalogItem`/`PartyRoleOption` shape is defined once (Task 5) and consumed by picker (7), RoleSelector (9), framing (13), banner (14). `domain_id` option name is consistent across `chat.ts`/`useChat.ts`/`ChatContainer` (Task 10).
