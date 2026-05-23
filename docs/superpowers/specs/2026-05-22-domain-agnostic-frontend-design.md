# Domain-Agnostic Frontend — Design

**Date:** 2026-05-22
**Status:** Approved (brainstorming) — pending implementation plan
**Related:** `2026-05-13-employment-tribunal-vertical-design.md` (employment domain corpus/eval work)

## Overview

The backend already models multiple legal domains: `packages/domain_core/domains/*.yaml` defines 5 domains (`housing.deposit.v1`, `employment_unfair_dismissal_v1`, `housing_property_chamber_rro_v1`, `housing_rent_determination_v1`, `housing_repairs_social_v1`), each with `party_roles`, `user_facing_name`, `stage`, `matter_types`, intake/prompt-pack references, and a retrieval namespace. The API threads `domain_id` through `/chat/start`, `/chat/bulk-intake`, and `/predictions/generate`.

The **frontend**, however, is hardcoded to housing tenancy-deposit disputes with `tenant`/`landlord` parties: the role selector, copy, `PartyRole` type, intake stages, and prediction/mediation framing all assume deposit. This design makes the frontend domain-driven and adds an explicit domain picker, so the app presents and runs any domain the backend exposes.

## Goals

- Frontend presents and runs **any** domain the backend exposes — no hardcoded `tenant`/`landlord`/`deposit` assumptions in user-facing flows.
- An **explicit domain picker** is the first step; it surfaces all 5 domains (deposit "live", the others "research/beta", anything not ready "coming soon").
- Backend **domain specs remain the single source of truth**; the frontend reads a catalog from the API rather than duplicating domain metadata.
- The existing **deposit flow is unchanged** (guided + bulk intake, prediction, mediation).

## Non-Goals

- Generalizing the **guided** step-by-step intake to non-deposit domains. Guided intake stays deposit-only; non-deposit domains use the free-text **bulk** intake. (Architecture still allows adding guided per-domain later.)
- Generalizing the backend **prediction outcome vocabulary** (`tenant_wins`/`landlord_wins` are housing-shaped). The frontend maps outcomes positionally to each domain's two party roles; true backend outcome-semantics generalization is a separate follow-up.
- Enabling the domain **router** / auto-classification. Selection is an explicit picker (`DOMAIN_ROUTER_ENABLED` stays false).
- Authoring new corpora/eval gates. We use the existing seed corpora in `data/indices/<namespace>/`.

## Background — current state

- **No `GET /domains` endpoint.** Domains load at startup via `packages/domain_core/registry.py:load_domain_specs()`; `get_domain_spec(id)` reads a single spec. `DomainSpec` (`packages/domain_core/spec.py`) exposes `id`, `display_name`, `user_facing_name`, `party_roles`, `stage`, `matter_types`.
- **`domain_id` threading exists.** `_resolve_domain_or_400()` (`apps/api/src/routers/chat.py`) → `resolve_domain_runtime()` (`apps/api/src/domain_runtime.py`), defaulting to `config.default_domain`. `ENABLED_DOMAINS` / `DEFAULT_DOMAIN` / `DOMAIN_STRICT_EVAL_GATES` in `apps/api/src/config.py`.
- **Party roles are machine strings only** — no display labels (deposit: `tenant`/`landlord`; employment: `claimant`/`respondent_employer`).
- **Frontend hardcoding** (work to do): `RoleSelector.tsx` (two fixed buttons), `lib/types/chat.ts` (`PartyRole = 'tenant' | 'landlord'`, deposit-specific `IntakeStage`), `lib/constants/stages.ts`, `IntakeSidebar.tsx` (deposit `getStageData()`), copy in `app/layout.tsx`/`app/page.tsx`/`MessageList.tsx`/`DisputeEntrySelector.tsx`/`InviteCodeDisplay.tsx`/`Footer.tsx`, and tenant/landlord framing in `OutcomeDisplay.tsx`/`IssuePredictionCard.tsx`/`ExpectationCard.tsx`.
- **Bulk intake is domain-agnostic** (free-text → extraction with the domain's prompt pack); guided intake uses hardcoded per-role prompts (`tenant_intake.py`/`landlord_intake.py`).

## Design

### 1. Backend — domain catalog endpoint

New `apps/api/src/routers/domains.py` mounting `GET /domains` (and optionally `GET /domains/{id}`). It serializes the registry — no new domain logic. For each domain in `ENABLED_DOMAINS`:

```jsonc
{
  "id": "employment_unfair_dismissal_v1",
  "user_facing_name": "Unfair dismissal",
  "family": "employment",
  "stage": "research",                       // production | beta | research | disabled
  "party_roles": [
    { "value": "claimant", "label": "Employee (claimant)", "blurb": "Bringing the claim" },
    { "value": "respondent_employer", "label": "Employer (respondent)", "blurb": "Responding to the claim" }
  ],
  "intake_modes": ["bulk"],                   // deposit -> ["guided","bulk"]; others -> ["bulk"]
  "availability": "research_beta",            // live | research_beta | coming_soon
  "blurb": "Predict likely Employment Tribunal outcomes from similar decisions.",
  "disclaimer_level": "research"              // standard | research
}
```

`availability` is **computed**, not hardcoded, and is the field the picker keys on. (Note: every spec currently carries `stage: research`, so `availability` is derived from baseline status + corpus/gate readiness, **not** from the `stage` label — `stage` is passed through for information only.)
- `live` — the baseline/default domain (`DEFAULT_DOMAIN` = deposit), which has the full corpus and passes its gate.
- `research_beta` — enabled, not the baseline, and has a usable prompt pack **and** a non-empty seed corpus/namespace.
- `coming_soon` — missing a prompt pack or corpus (rendered disabled). This keeps the picker honest if a non-deposit domain isn't actually runnable yet.

`intake_modes` is `["guided","bulk"]` only for domains with a guided-intake implementation (deposit today); everything else is `["bulk"]`.

### 2. Backend — party-role labels

Add `party_role_labels` to each domain YAML (the only new spec field), mapping each `party_roles` value to a human label and optional blurb:

```yaml
party_roles: [claimant, respondent_employer]
party_role_labels:
  claimant: { label: "Employee (claimant)", blurb: "Bringing the claim" }
  respondent_employer: { label: "Employer (respondent)", blurb: "Responding to the claim" }
```

`DomainSpec` parses it; the catalog endpoint emits it. Backend role validation (currently `if request.role not in ("tenant","landlord")`) changes to validate against the resolved domain's `party_roles`.

### 3. Frontend — DomainContext + picker

- **Picker** is a new first step in `/chat` (before role selection). It fetches `GET /domains` and renders cards grouped by `availability`: live first, then research-beta (with a badge), then disabled "coming soon". Selecting a domain advances to role selection.
- **`DomainProvider` / `useDomain()`** (`apps/web/lib/context/`) holds the selected domain summary, persisted to localStorage and reflected in `domain_id`. Resume/refresh restores it; a session's domain is read back from the case file's `domain_id` when resuming.
- **Copy is context-driven.** `RoleSelector`, `MessageList` greeting, `DisputeEntrySelector` subtitle, `InviteCodeDisplay`/share copy, `Footer`, and `app/layout.tsx` metadata read `user_facing_name`/labels from context. Layout title becomes domain-neutral ("Proposer — AI dispute resolution"); per-page copy uses the active domain's `user_facing_name`.
- **Types:** `PartyRole` widens from `'tenant' | 'landlord'` to `string`; role comparisons that branched on `'tenant'`/`'landlord'` switch to the domain's `party_roles` ordering (first vs second party).

### 4. Frontend — intake routing by domain

- Deposit (`intake_modes` includes `guided`): unchanged — mode selector → guided or bulk.
- Non-deposit (`intake_modes: ["bulk"]`): skip the mode selector, go straight to the bulk-paste form; hide the deposit-shaped guided `IntakeSidebar` stage walk. Bulk intake already returns `case_file` + completeness + the "Get Prediction" affordance.
- `domain_id` is sent on `/chat/start`, `/chat/bulk-intake`, and `/predictions/generate`.

### 5. Frontend — generalize prediction/mediation framing

`OutcomeDisplay`, `IssuePredictionCard`, `ExpectationCard`, and the mediation cost-benefit replace literal "Tenant"/"Landlord" wording with the active domain's role **labels**, mapped **positionally**: the already-canonical `*_wins` outcome (`tenant_wins`/`landlord_wins`, fixed earlier) maps to `party_roles[0]` favoured / `party_roles[1]` favoured. For deposit this is identical to today; for employment it reads "Employee (claimant) favoured".

### 6. Readiness & disclaimers

- `.env` (local): expand `ENABLED_DOMAINS` to all 5; keep `DOMAIN_STRICT_EVAL_GATES=false` locally so research domains run.
- Research-beta domains show a prominent "Research/beta — predictions are experimental" disclaimer on the intake, prediction, and mediation screens (driven by `disclaimer_level`).

## Data flow

Picker → `GET /domains` → user selects domain → `DomainContext` set + `domain_id` persisted → role selection (from `party_roles`) → intake (`/chat/start` or `/chat/bulk-intake` with `domain_id`) → prediction (`/predictions/generate` with `domain_id`) → mediation. All screens read labels/copy from `DomainContext`.

## Units & boundaries

- **`domains` router** (backend): read-only serialization of the registry. Input: config + registry. Output: catalog JSON. No write paths.
- **Catalog client + `DomainContext`** (frontend): single fetch + provider; consumers depend only on the context shape, not on any domain literals.
- **`RoleSelector`, intake router, framing components**: each consumes `DomainContext`; none contains domain literals after the change.

## Testing

- **Backend unit:** `GET /domains` returns the enabled domains with correct `availability`, `party_roles` labels, and `intake_modes`; role validation accepts a domain's roles and rejects foreign ones.
- **Browser E2E (Claude-in-Chrome):**
  - Deposit: picker → tenant → guided + bulk → prediction → mediation still works (regression).
  - Employment (research-beta): picker shows badge + disclaimer → claimant → bulk paste → prediction renders with "Employee (claimant)" framing → mediation.
  - A "coming soon" domain is disabled in the picker.
- **API chain:** bulk-intake + prediction for one non-deposit domain end-to-end.

## Risks & assumptions

1. **Non-deposit runnability.** Bulk intake + prediction must produce usable output for a research-beta domain against its seed corpus + prompt pack. Validate this **first** in implementation; if a domain lacks a prompt pack or has too-thin a corpus, the catalog marks it `coming_soon` rather than `research_beta`.
2. **Housing-shaped outcome vocabulary.** The pipeline emits `tenant_wins`/`landlord_wins` regardless of domain; the frontend maps positionally. Semantically-correct per-domain outcome labels in the *backend* are a follow-up.
3. **Guided intake** remains deposit-only by design; non-deposit relies entirely on bulk extraction quality.
4. **Shared dev DB / worktree.** Testing uses the symlinked corpus and the shared local Postgres (see memory: worktree-corpus-setup).

## Rollout

Frontend + the read-only `/domains` endpoint + the `party_role_labels` spec field ship together. Production enablement of each non-deposit domain stays gated on its eval/launch artifacts (unchanged policy).

## Decision log

**2026-05-23 — availability honors the launch gate (supersedes the earlier "research-beta runnable" framing).** During implementation (plan Task 4) the runnability check found all four non-deposit domains fail closed on the user-facing request path: `_STAGE_MODES` (domain_runtime.py) only permits `requested_mode="research"` for `stage: research` domains, while user-facing calls use `production` mode — so they 403 (`gate=disabled, allowlist=blocked`), independent of `ENABLED_DOMAINS` or `DOMAIN_STRICT_EVAL_GATES`. Per the project's fail-closed philosophy, the user chose to **honor the gate** rather than add a local research-mode bypass. Consequences:
- `_availability` is computed from `resolve_domain_runtime(id, requested_mode="production").is_usable`: `live` if usable, else `coming_soon`. Deposit is `live`; the four research domains are `coming_soon` (visible but disabled in the picker).
- `ENABLED_DOMAINS` reverts to deposit-only; the catalog lists *all registered* domains regardless, so the picker still shows the full set.
- `research_beta` remains a valid catalog value for a future genuinely-runnable beta domain, but is not produced today. The research/beta disclaimer banner (plan Task 14) is therefore dormant until such a domain exists — keep it minimal or defer it.
- Risk #1 above is resolved by this gate-driven computation: non-runnable domains can never appear selectable.

**2026-05-23 — plan Tasks 13 (positional prediction/mediation framing) and 14 (research/beta banner) deferred.** Consequence of the gate decision: only deposit is selectable, so (a) the research/beta banner has no domain to trigger it, and (b) generalizing the prediction/mediation party framing produces zero visible change for deposit while risking regression of the outcome-label fixes shipped this session. Both are pure forward-looking work that should land **together with** the backend outcome-vocabulary generalization (Non-Goals / Risk #2) when the first non-deposit domain is actually promoted to runnable. Implemented this session: Tasks 1–12 (backend catalog + party labels + role validation + gate-driven availability; frontend catalog/context/picker/role-selector/domain_id threading/bulk-routing/copy).
