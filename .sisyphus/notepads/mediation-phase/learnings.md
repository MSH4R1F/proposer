# Mediation Phase — Learnings

## [2026-03-06] Session ses_33f759828ffew3i301FxyRKBh9

### Codebase Conventions
- Python: Pydantic BaseModel with `model_dump(mode='json')`, enums as `str, Enum`
- Timestamps: `datetime.now().isoformat()` as string, stored in Field with `default_factory`
- IDs: `str(uuid4())[:8].upper()` pattern (short IDs, see dispute.py line 68)
- DisputeCase already has: READY_FOR_MEDIATION, IN_MEDIATION, SETTLED, CLOSED statuses
- `update_timestamp()` pattern for mutating models (see dispute.py line 92)
- `mark_party_complete()` is the reference idempotent status transition pattern

### Frontend Conventions
- api client exports `api` (NOT `apiClient`) — import as `import { api } from './client'`
- predictionsApi pattern: `export const mediationApi = { method: (params) => api.get/post(...) }`
- types/index.ts uses `export * from './filename'`
- api/index.ts exports named exports: `export { mediationApi } from './mediation'`
- hooks/index.ts: `export { hookName } from './hookFile'`
- routes.ts: function routes like `(id: string) => \`/path/${id}\``

### Key File Locations
- Dispute model: `packages/llm_orchestrator/models/dispute.py`
- Conversation model: `packages/llm_orchestrator/models/conversation.py` (Message pattern)
- Frontend types pattern: `apps/web/lib/types/chat.ts`
- API client base: `apps/web/lib/api/client.ts` (exports `api`)
- Routes: `apps/web/lib/constants/routes.ts`

## [2026-03-06] Task 2: Frontend Types + API Client
- mediationApi exported from apps/web/lib/api/index.ts
- All types exported from apps/web/lib/types/index.ts
- downloadSettlementPDF returns URL string (not async) for use as href
- 4 new routes added to ROUTES constant (MEDIATION_EXPECTATION, MEDIATION_CHAT, MEDIATION_SETTLEMENT, MEDIATION_ESCALATION)
- TypeScript compilation passes with zero errors
- All mediation types follow exact pattern from chat.ts and prediction.ts
- API client methods follow exact pattern from predictions.ts

## [2026-03-06] Task 3: Tribunal Cost Data Module
- packages/llm_orchestrator/data/ package created with __init__.py
- TribunalCostComparison: tenant_costs=0, landlord_costs=[200,500], timeline=[6,12]
- get_cost_benefit_analysis(role, prediction_data) raises ValueError for invalid role
- CostBenefitAnalysis has convenience properties: tenant_costs, landlord_costs_min/max, timeline_months_range
- Role-specific framing: tenant emphasizes "recover" and "no fees", landlord emphasizes "costs" and "pay back"
- All tests passing: tenant, landlord, and invalid role error handling

## [2026-03-06T01:34:51Z] Task 1: Backend Mediation Data Models
- MediationSession created with submit_offer, accept_offer, reject_offer, counter_offer, settle, escalate
- StructuredOffer validates amount >= 0 (and <= deposit_amount if provided)
- accept_offer validates responder != proposer to prevent self-acceptance
- DisputeCase.start_mediation() only allows from READY_FOR_MEDIATION or BOTH_COMPLETE
- All models serialize via model_dump(mode='json')

## [2026-03-06] Task 4: Mediation Service Lifecycle
- Singleton pattern mirrored dispute service: `_mediation_service` + `get_mediation_service()` factory
- Session persistence path is `config.data_dir / "mediations"` with filenames `mediation_{dispute_id}.json`
- File writes use `fcntl.flock(..., LOCK_EX)` with truncate + JSON dump for append-only runtime operations
- Service resolves party role by dispute-linked `tenant_session_id`/`landlord_session_id`
- Offer response flow enforces opposite-party responder and supports accept/reject/counter transitions

## [2026-03-06] Task 5: AI Mediator Agent + Prompt
- New prompt module added at `packages/llm_orchestrator/prompts/mediator.py` with strict information-only framing and explicit non-advice disclaimer.
- Mediator methods implemented in `packages/llm_orchestrator/agents/mediator_agent.py` with async LLM calls using system+user prompt pattern.
- `calculate_zopa(prediction)` prioritizes `predicted_settlement_range` and returns `{min,max,center}` with safe fallbacks.
- `calculate_possible_counter_range(prediction, current_offer, role)` constrains counters to ZOPA to keep movement realistic.
- Prompt compliance verified: contains informational/non-advice language and excludes forbidden advisory phrases.

## [2026-03-06] Task 9: Mediation React Hooks
- Created 3 hooks: useMediationExpectation, useMediationChat, useMediationSettlement
- useMediationExpectation: Fetches expectation data on mount, returns { expectationData, isLoading, error, refresh }
- useMediationChat: Fetches initial messages, polls every 10s with setInterval, cleanup via clearInterval in useEffect return
  - Provides: sendMessage, submitOffer, respondToOffer methods
  - Tracks lastUpdated timestamp for UI indicators
  - Uses useAutoScroll for auto-scroll on new messages
  - Returns messagesContainerRef for DOM attachment
- useMediationSettlement: Fetches settlement data on mount, returns { settlement, isLoading, error, refresh }
- All hooks follow usePrediction.ts pattern (useState + useCallback + useEffect)
- Polling pattern: useRef to store interval, useEffect with cleanup function
- TypeScript compilation: zero errors
- All hooks exported from apps/web/lib/hooks/index.ts

## [2026-03-06] Task 6: Mediation API Router (8 endpoints)
- Router prefix: `/mediation` (NOT `/mediation/{dispute_id}`) — path param in each route, not prefix
- `routers/__init__.py` must NOT do `from apps.api.src.routers import ...` — that causes circular import when running tests from `apps/api`; keep it to `__all__` only
- Import verification command: `cd apps/api && PYTHONPATH=../../packages:../.. python3 -c "from src.routers.mediation import router; print('OK')"`  (both packages AND project root in PYTHONPATH)
- ValueError → 400 for POST endpoints (bad request: invalid state, wrong party, bad amount)
- ValueError → 404 for GET endpoints that return "not found" (expectation, settlement, PDF)
- `submit_offer` returns `StructuredOffer` object → serialize via `.model_dump(mode="json")` before returning
- `generate_settlement_pdf` returns raw bytes → wrap in `fastapi.Response(content=..., media_type="application/pdf")`
- `get_messages` uses `Optional[str] = Query(None, ...)` for the `since` timestamp parameter
- All 8 endpoints follow exact chat.py pattern: `logger.debug` on entry, `logger.info` on success mutations, `logger.warning` on expected errors, `logger.error` on unexpected exceptions
- `response_model` not needed — returning `Dict[str, Any]` / `List[Dict[str, Any]]` is fine for complex nested service responses

## [2026-03-06] Task 7: Expectation Adjustment Page + Mediation Layout
- Mediation layout: simple server component (no 'use client'), wraps children with header + main
- Expectation page: 'use client', splits into outer page (use(params)) + inner component (useSearchParams) wrapped in Suspense
- Suspense is required for useSearchParams in Next.js 15 even in client components
- ExpectationData type uses `prediction_summary` not `prediction` — always verify actual type vs task description
- ExpectationData.prediction_summary.overall_confidence is a fraction (0-1), multiply by 100 for display
- CostBenefitTable: cost_to_party can be number | [number, number] — use Array.isArray() to discriminate
- AcceptancePrompt: mediationApi.startMediation is async, await before router.push to settlement
- Prediction page: useSearchParams added with 'Proceed to Mediation' button shown when prediction is non-null
- TypeScript: zero errors with all new files; unused Suspense import must be removed if not used

## [2026-03-06] Task 10: Settlement and Escalation Pages
- SettlementSummary type uses `agreed_amount` (NOT `settlement_amount`) — verify actual type vs task description
- `mediationApi.downloadSettlementPDF(disputeId)` returns a URL string synchronously — use directly as `href` in anchor tag
- DownloadButton: uses `<a href download>` with onClick to briefly set `isDownloading=true`; reset after 2s timeout since browser handles actual download
- Escalation page is static — no data fetching, no `use(params)` needed (params not used)
- Next.js 15 async params: use `use(params)` pattern to unwrap Promise, consistent with prediction page
- `SettlementSummary` component name collides with type name — import type as `SettlementSummaryType` in the component file
- `LegalDisclaimer` was NOT reused — inline disclaimer pattern used instead to match specific copy requirements; both approaches are valid
- TypeScript compilation: zero errors with all 5 new files
- Evidence saved to `.sisyphus/evidence/task-10-tsc.txt`

## [2026-03-06] Task 8: AI Mediator Chat Page
- chat/page.tsx pattern: outer component uses `use(params)` + Suspense wrapper, inner component uses `useSearchParams()`
- Role not provided by useMediationChat hook — derive from `searchParams.get('role') || ''` in page, pass as `currentRole` optional prop to MediationChat
- `useAutoScroll` returns `RefObject<T | null>` — MediationChat types `messagesContainerRef: RefObject<HTMLDivElement | null>` which is compatible with `<div ref={...}>`
- `() => Promise<T>` is assignable to `() => void` in TypeScript — onRefresh/onSendMessage typed as `void`-returning work fine
- OfferCard canRespond guard: `currentRole !== offer.proposed_by_role && offer.status === 'pending'` — both conditions needed
- Settlement detection: `offers.some(o => o.status === 'accepted')` not from messages
- Escalation detection: check system messages containing 'escalat' (substring match covers 'escalated', 'escalation')
- MediationMessageBubble is a pure server-friendly component (no 'use client' needed — no hooks, no events)
- Empty state in message list: show only when `messages.length === 0 && !isLoading`
- Initial loading gate: show loader only when `isLoading && messages.length === 0` to avoid hiding messages during polling
- Error state: show full error UI only if `error && messages.length === 0`; inline error banner otherwise
- TypeScript: zero errors — all 6 new files compile cleanly

## [2026-03-06] Task 11: Settlement PDF Generation with reportlab
- `apps/api/src/utils/` package created with empty `__init__.py`
- `generate_settlement_pdf(settlement_data: dict) -> bytes` uses `reportlab.pdfgen.canvas` + `io.BytesIO`
- reportlab pattern: `buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4); ...; c.save(); return buf.getvalue()`
- Import reportlab inside the function body (lazy import) to avoid import errors if reportlab not installed at module load time
- `mediation_service.generate_settlement_pdf` calls `get_settlement(dispute_id)` first (raises ValueError if not settled), then passes result to pdf util
- Router already had correct `Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": ...})` — no router changes needed
- Disclaimer box: use `c.rect(x, y, w, h, fill=1, stroke=1)` with red stroke + light pink fill for prominence
- Text wrapping: manual word-wrap loop (split by words, accumulate until line exceeds char limit)
- `reportlab>=4.0.0` added to requirements.txt under new `# PDF generation` section
- Import verification: `PYTHONPATH=packages python3 -c "from apps.api.src.utils.pdf_generator import generate_settlement_pdf; print('OK')"` → OK

## [2026-03-06T02:26:31Z] Task 12: Mediation API pytest suite
- Added  with isolated MediationService fixture patching dispute/intake/prediction getters to prevent external dependencies and API calls
- Added 18 async service tests in  covering start, expectation framing, messaging, offers, respond actions, polling, escalation, and guardrail failures
-  fixture provides AsyncMock canned responses; no Anthropic key required for this suite
- Test runs verified with and without , both passing 18/18
- Evidence captured at  and 

## [2026-03-06T02:26:39Z] Task 12: Mediation API pytest suite
- Added `apps/api/tests/conftest.py` with isolated MediationService fixture patching dispute/intake/prediction getters to prevent external dependencies and API calls
- Added 18 async service tests in `apps/api/tests/test_mediation.py` covering start, expectation framing, messaging, offers, respond actions, polling, escalation, and guardrail failures
- `mock_claude_client` fixture provides AsyncMock canned responses; no Anthropic key required for this suite
- Test runs verified with and without `ANTHROPIC_API_KEY`, both passing 18/18
- Evidence captured at `.sisyphus/evidence/task-12-pytest-results.txt` and `.sisyphus/evidence/task-12-no-api-key.txt`
