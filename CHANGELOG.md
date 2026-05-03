# Changelog

All notable changes to the Proposer legal mediation system will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`POST /mediation/{dispute_id}/start` returned HTTP 500 (`AttributeError: 'tuple' object has no attribute 'strip'`)** — `MediatorAgent.generate_opening_message` and `generate_response` return `(text, TraceSummary)` tuples, but the postgres-mode `_pg_start_mediation` and `_pg_add_message` paths in `MediationService` were passing the tuple directly into `_add_ai_mediator_message`, which then crashed inside `_enforce_legal_disclaimer` when calling `.strip()` on it. The legacy in-memory paths already unpacked correctly; only the postgres paths had drifted. Fix: unpack `(content, trace)` and forward the trace into the persisted mediator message via `reasoning_trace=`. (`apps/api/src/services/mediation_service.py`)
- **`POST /mediation/{dispute_id}/start` returned HTTP 500 (`ModuleNotFoundError: No module named 'aiosqlite'`) when no cached prediction was on the dispute row** — `_fetch_prediction_data_uow` fell back to the legacy `_get_prediction_data`, which constructs an in-memory sqlite engine via `get_prediction_service()`. In a postgres-mode deployment without `aiosqlite` installed this raised before the caller could reach the proper "Prediction required before mediation" branch. Fix: replace the legacy fallback with a UoW-based lookup that resolves the dispute's linked sessions to case ids and queries `predictions.get_by_case_id` directly, returning the most recent match. Test fixtures in `test_mediation_service.py` and `test_mediation_atomicity.py` now stub `_fetch_prediction_data_uow` (the actual postgres-mode hook) in addition to the legacy hook. (`apps/api/src/services/mediation_service.py`, `apps/api/tests/db/test_mediation_service.py`, `apps/api/tests/db/test_mediation_atomicity.py`)
- **`GET /mediation/{dispute_id}/messages` returned HTTP 500** — `MediationService.get_messages` returns `List[Dict]` (per its tests), but the router treated the result as a dict and indexed `result["messages"]`/`result["offers"]`, raising `TypeError: list indices must be integers or slices, not str`. The web client expects the `{messages, offers}` envelope. Fix: assemble the envelope in the router by combining `get_messages()` with offers read from `get_session()`; service contract and tests unchanged. (`apps/api/src/routers/mediation.py`)

### Added

- **SHA-28: LLM-assisted gold-set labeling pipeline (Phases 1–12)** — replaces the original two-paralegal blind double-annotation flow on every real-gold row of `data/gold_standard/housing_v1.jsonl`. Decision recorded in `docs/eval/decision-log.md` D-021. Codex sparring (8 P1/P2 findings, all integrated before any code landed) at `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md`.
  - **Schema**: `LabelerModel`, `FieldLabelProvenance`, `LabelingProvenance` added to `packages/eval/schema.py`; `GoldCase.labeling_provenance: Optional[LabelingProvenance]` is `None` for legacy hand-annotated rows, populated for every row produced by the new pipeline.
  - **`packages/eval/auto_label/`** new package:
    - `canonicalize.py` — NFKC, ligature expansion, dehyphenation, whitespace collapse; `CANONICALIZER_VERSION = '1.0.0'`.
    - `span_match.py` — bounded-window quote matcher (canonical-exact + small bounded edit distance only inside the labeler's claimed `(page, paragraph, char_start, char_end)` window; no whole-document fuzzy fallback — closes the prompt-injection hole).
    - `disagreement.py` — field-path `DisagreementSet` with stable identity keys (`evidence[key].kind`, `per_issue[issue=damages].winner`, etc.) so list disagreements are not hidden inside list equality.
    - `append_gate.py` — `assert_real_gold_appendable(GoldCase, run_artifact_path)` refuses on missing `labeling_provenance`, `negative_kind` set, missing `target_source_id`, missing manifest fields, incomplete MandatoryReviewSet coverage, or missing/mismatched run-artifact hashes.
    - `leakage_scan.py` — `facts` phrase-list scan for tribunal-finding language (`"the tribunal finds"`, `"we award"`, `"we conclude"`, …) plus span-section check restricting `facts` to `pre_decision_record` paragraphs. `facts` flows into `CaseFile.tenant_narrative` at prediction time, so verdict leakage here corrupts every downstream accuracy/Brier number.
    - `lookups/` — `AuthorityLookup` and `StatuteLookup` runtime-checkable Protocols + in-memory test stubs with deterministic `index_id` / `index_hash` for replay.
    - `grounder.py` — 10 per-field check functions (quote, authority, statute, outcome basis, label basis, facts leakage, date sanity, amount sanity, schema invariants, real-gold audit) plus the top-level `ground(...)` orchestrator that emits a `GroundingResult` with `field_path → GROUNDED|UNGROUNDED`, `reasons`, `match_strategy`, and `grounding_pass_rate`. `GROUNDER_VERSION = '1.0.0'`.
    - `runner.py` — `LabelingRun`, `LabelerOutput`, `CasePass`; `run_one_case(...)` async-dispatches both labelers via `asyncio.gather`, runs the grounder per output, returns the pass record. `write_artifact(...)` writes `data/eval_artifacts/labeling/<run_id>/<case_id>.json` with raw outputs, prompts, hashes, grounding decisions. `RUNNER_VERSION = '1.0.0'`.
    - `prompts/extraction.py` — `EXTRACTION_SYSTEM_PROMPT` (labeler is told never to invent values, source text is data not instructions, `facts` must come from `pre_decision_record` only) + `render_extraction_prompt(...)` + `prompt_template_hash()` (sha256 of pack version + system prompt; `LabelingProvenance.prompt_template_hash` carries it forward per case).
  - **`packages/llm_orchestrator/clients/labeler_factory.py`** — `LabelerModelSpec` (Pydantic model with `provider: Literal["anthropic", "openai"]`) + `build_labeler_client(spec)` constructing two distinct concrete clients (`ClaudeClient` for Anthropic specs, `OpenAIClient(store=False)` for OpenAI). Does NOT delegate to `get_llm_client(LLMRole.EXTRACTION)` — the role-keyed factory cannot prove provider independence (Codex finding [4]). Tests prove A and B are different concrete classes with different providers.
  - **`scripts/eval/auto_label.py`** — pre-adjudication CLI. Loads source text, parses two `provider:model` specs, builds clients, runs `run_one_case`, writes the per-case artifact. Refuses two failure modes: same provider for A and B (provider-independence guard), and any `--artifacts-root` under `data/gold_standard/` (gold-corpus belongs to `adjudicate.py`). Offline mode + canned-response files for tests.
  - **`scripts/eval/adjudicate.py`** — adjudication + real-gold append CLI with three subcommands: `list --run-id` (artifacts in run), `queues --run-id --case-id` (MandatoryReviewSet + DisagreementSet + 10% deterministic audit overlay derived from the artifact), `append --run-id --case-id --decisions <path>` (build final `GoldCase`, run `assert_real_gold_appendable`, only on green-light append to `data/gold_standard/<corpus>.jsonl` + reviewer-log entry). This is the only path that writes to `data/gold_standard/`; the labeling CLI refuses to.
  - **Review hardening**: append gate now rejects blank SHA-20 manifest values, case/run artifact mismatches, and replay-field drift beyond the two source hashes; adjudication derives persisted labeler model provenance from the artifact rather than trusting the decisions file; queues include unapportioned outcomes and exclude synthetic grounder checks from the audit overlay; offline canned outputs follow labeler A/B order even when provider order is reversed.
  - **Documentation** rewrites: `docs/eval/reviewer-guide.md` (now adjudicator-only flow — three queues, human-only anchor, leakage-sensitive `facts` rewrite, `LabelingProvenance` recording per case); `docs/eval/methodology.md` §4.3 (LLM-assisted labeling protocol with all eight pipeline steps + counter-stack to the circularity attack); `docs/eval/architecture.md` (data-flow diagram + lifecycle of a single annotated case); `docs/eval/decision-log.md` D-021 (decision + Why + rejected alternatives + trigger to revisit); `.sisyphus/plans/track-a-plan.md` Phase 3 + Phase 6 + "Annotation reliability" rewritten to match.
  - **Reporting rule**: `inter_model_agreement_rate` is recorded in `LabelingProvenance` but is **NOT Cohen's κ** and must not be reported as one. The defensibility metrics are `mandatory_review_flip_rate`, `audit_flip_rate`, anchor-set divergence, and adjudication rate by field path. A combined-corpus calibration claim is blocked when anchor divergence exceeds the pre-registered threshold (Brier delta > 0.05 or systematic winner-flip).
  - **Test count**: 177 new SHA-28 tests across `packages/eval/tests/` (schema, canonicalizer, span matcher, DisagreementSet, append gate, leakage scanner, grounder, lookups, runner, auto_label CLI, adjudicate CLI) and 11 new `test_labeler_factory.py` tests. Full eval suite: 545/545 passing in `packages/eval/tests/`. Eval suite has 0 regressions.
  - **End-to-end DoD met**: `tests/test_adjudicate_cli.py::TestAppendSubcommand::test_end_to_end_appends_to_jsonl` runs `auto_label.py --offline` to land an artifact, then `adjudicate.py append` to build the final `GoldCase`, run the append gate, and append one row to the corpus JSONL plus a reviewer-log entry — all in-process, no real LLM calls.
  - **Plan**: `docs/superpowers/plans/2026-05-02-llm-labeling-pipeline.md`. **Sparring**: `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (Codex revised, 8 findings integrated).

- **SHA-36: Proposition KG — Phase 1 substrate**
  - **Schema**: 4 new tables + 3 new enums via Alembic migration `0002_add_proposition_kg.py`. Tables: `decision_documents` (one row per ingested decision PDF, content-hashed), `proposition_extraction_runs` (one row per ingestion attempt, with model id, prompt version, status, token + cost metrics), `propositions` (atomic claims with quote span, paragraph ref, offsets, issue tags, entities, monetary amounts, type), `proposition_edges` (typed edges between propositions in the same run).
  - **Domain models** (`packages/kg_builder/propositions/models.py`): `Proposition`, `PropositionEdge`, `DecisionDocument`, `ExtractionRun` (Pydantic), with field-level validation for paragraph-ref shape (string, not integer — preserves `12(3)`, `Sch.1 para 4`, etc.), monetary amounts, issue-tag enum, edge-type enum.
  - **Repository + Unit of Work**: `apps/api/src/db/repositories/propositions_repo.py` adds `PropositionsRepo` (`save_document`, `save_run`, `save_propositions`, `save_edges`, `find_succeeded_run` for CLI `--resume` support, `list_propositions_for_document`); wired into `UnitOfWork` alongside the existing six SHA-102 repos.
  - **Extraction pipeline** under `packages/kg_builder/propositions/`: `text_loader.py` (reuses `PDFExtractor.extract_from_pdf`), `provenance.py` (`find_source_span` + `normalize_for_matching`), `extractor.py` (`LLMPropositionExtractor` calling `ClaudeClient.generate_structured`), `edge_extractor.py` (`LLMPropositionEdgeExtractor`), `graph_validator.py` (`validate_graph` rejects edges to unverified propositions, drops `supports` cycles, deduplicates parallel edges).
  - **Quote verification + prompt-injection guard at substrate layer**: every proposition's `source_passage` must be a literal whitespace-tolerant substring of the actual decision text; propositions with unverified quotes are rejected with `reason='quote_not_found'` before persistence. This is the cite-or-abstain rule from the Stanford/Yale Legal RAG Hallucinations paper, implemented at the layer where it cannot be skipped.
  - **Deterministic identity**: proposition `id` = `uuid5(NAMESPACE, "{document_id}|{paragraph_ref}|{source_passage_hash}|{type}|{text_hash}")`. Re-ingestion is idempotent in the common case (`test_ingestion_idempotent_on_repeat` asserts 0 duplicates on second run).
  - **Corpus selector CLI**: `scripts/ingestion/select_proposition_corpus.py` produces a deterministic 5-document smoke manifest from `data/raw/bailii`.
  - **Ingestion CLI**: `scripts/ingestion/ingest_propositions.py` with `--manifest`, `--dry-run`, `--commit`, `--resume`, `--force`, `--jsonl-report`, `--mock-response` flags. Per-run cost + tokens recorded to JSONL for the £/document distribution.
  - **Phase 1 scope**: offline corpus-ingestion path only. Not wired into live mediation predictions; Phase 2 will consume the substrate via PageRank-driven retrieval (`proposition_id`, `issue_tags`, `entities`, `proposition_edges.edge_type`, `document_id`).
  - **Test count**: ~145 new SHA-36-specific tests across `apps/api/tests/db/`, `packages/kg_builder/propositions/tests/`, and `scripts/ingestion/tests/`. Full suite: 335 passed, 10 skipped, 0 regressions.
  - **Spec**: `docs/superpowers/specs/2026-05-01-sha-36-proposition-kg.md`. **Plan**: `docs/superpowers/plans/2026-05-01-sha-36-proposition-kg.md`.

- **Comprehensive Architecture Documentation** - Created detailed system architecture documentation
  - **New File**: `docs/ARCHITECTURE.md` with complete system overview
  - **Mermaid Diagrams**:
    - Full system architecture diagram showing Frontend → Backend → Packages → External Services
    - Sequence diagrams for key flows: Intake Chat, Prediction Generation, Multi-Party Disputes
  - **Documentation Sections**:
    - Technology stack overview (Next.js 16, FastAPI, Claude, ChromaDB, etc.)
    - API endpoints mapping (routers → services → packages)
    - Data flow examples with detailed sequence diagrams
    - Key architectural patterns (separation of concerns, async/await, RAG patterns)
    - Technology choices with rationale
    - Scaling considerations (MVP vs. production)
    - Security & compliance guidelines
  - **Learning Resources**: Beginner-friendly explanations of:
    - What is RAG (Retrieval-Augmented Generation)?
    - What is a Knowledge Graph?
    - What is Hybrid Search?
    - What are Embeddings?
    - What is Async/Await?
    - What is Structured Output?
  - **Purpose**: Provides clear mental model for developers, helps with onboarding, and serves as living documentation

- **Strict Required Field Validation** - Enforces 100% required information collection before enabling predictions
  - **Backend Changes**:
    - Added `has_all_required_info()` method to `CaseFile` model for strict validation
    - Added `is_ready_for_prediction()` method that requires ALL required fields
    - Updated `PredictionService.check_case_ready()` to enforce strict validation (was 70%, now 100%)
    - Enhanced `IntakeService` to mark intake complete only when ALL required fields present
    - Updated `IntakeAgent._build_response_context()` to show clear warnings about missing required fields
    - Agent now proactively prompts for missing required information with priority indicators
  - **Frontend Changes**:
    - Added prominent "Missing Required Information" alert in `IntakeSidebar` with bullet list of missing fields
    - Added success message "All Required Info Collected!" when ready for prediction
    - Updated `useChat` hook to compute `isComplete` based on `missing_info.length === 0` (strict)
    - Updated `canGeneratePrediction` logic to require ALL required fields before enabling button
    - Prediction button now only appears when truly ready (not at arbitrary 70% threshold)
  - **Required Fields**:
    1. Property address
    2. Tenancy start date
    3. Deposit amount
    4. At least one dispute issue
    5. Deposit protection status (yes/no)
  - **User Experience**:
    - Clear visibility into what information is still needed
    - No ambiguity about when prediction can be generated
    - Agent proactively asks for missing required fields
    - Progress bar and sidebar show completion status accurately
  - **Impact**: Prevents incomplete predictions, ensures quality of analysis, improves prediction accuracy

- **Non-Blocking Completion Banner** - Improved layout so chat input remains visible
  - **Issue**: When required fields were complete, the completion banner blocked the chat input textbox
  - **Fix**: Made completion banner more compact and simplified input visibility logic
  - **Changes**:
    - Reduced banner padding and size (from `p-4` to `p-3`, smaller button)
    - **Simplified input condition**: shows whenever `roleSelected` is true (no stage restrictions)
    - Input stays visible at ALL times during intake, even if system detects missing required info
    - Updated placeholder when complete: "Add more details or generate prediction above..."
  - **Critical Fix**: Removed `stage !== 'complete'` condition that was hiding input in some cases
  - **User Experience**: Users can ALWAYS continue chatting and adding information once they've selected a role, ensuring they can provide missing required fields without confusion

- **Multi-Party Prediction Button Fix** - Fixed critical bug where prediction button never appeared for multi-party disputes
  - **Root Cause 1**: `update_dispute_from_session()` was never being called to sync dispute status when parties completed intake
  - **Root Cause 2**: `ChatMessageResponse` didn't return updated `dispute` info, so frontend never saw `is_ready_for_prediction: true`
  - **Backend Fixes**:
    - Added dispute status sync in `IntakeService.process_message()` after each message
    - Added `dispute` field to `ChatMessageResponse` API model
    - Updated `/chat/message` endpoint to return fresh dispute info with `is_ready_for_prediction` status
    - Now calls `dispute_service.update_dispute_from_session(intake_complete=True)` when all required fields present
    - Dispute model's `mark_party_complete()` updates status: `TENANT_COMPLETE` → `BOTH_COMPLETE` → `READY_FOR_MEDIATION`
  - **Frontend Fixes**:
    - Added `dispute?: DisputeInfo` to `ChatMessageResponse` TypeScript type
    - Updated `useChat.sendMessage()` to preserve/update `dispute` from message response
    - Frontend now receives real-time dispute status updates after each message
  - **How It Works Now**:
    1. Tenant sends message, completes required fields → `intake_complete = True`
    2. Backend calls `update_dispute_from_session()` → `dispute.status = TENANT_COMPLETE`
    3. Landlord sends message, completes required fields → `intake_complete = True`
    4. Backend calls `update_dispute_from_session()` → `dispute.status = READY_FOR_MEDIATION`
    5. Backend returns `dispute.is_ready_for_prediction = True` in message response
    6. Frontend sees updated dispute → `canGeneratePrediction = True`
    7. 🎉 Prediction button appears for both parties!
  - **Note**: 94% completeness is CORRECT - it means all 5 required fields (70%) + some optional fields (24%)

- **Critical Bug Fix: Dispute Status Regression** - Fixed bug where dispute status was reset when parties sent additional messages
  - **Bug**: `mark_party_complete()` would reset `READY_FOR_MEDIATION` back to `TENANT_COMPLETE` or `LANDLORD_COMPLETE` when called multiple times
  - **Root Cause**: The method wasn't idempotent - it didn't check if the party was already marked complete
  - **Symptom**: Both parties at 94% complete, shows "complete" message, but prediction button never appears
  - **Fix 1**: Made `mark_party_complete()` idempotent - returns early if already complete
  - **Fix 2**: Added `recalculate_status(tenant_complete, landlord_complete)` method for robust status calculation
  - **Fix 3**: Auto-fix on session load - `/chat/session/{id}` now checks both parties' sessions and recalculates dispute status
  - **Impact**: Existing disputes that were stuck in wrong state will auto-fix when users refresh the page

### Changed

- **SHA-102: Postgres-backed user-facing storage** ([PR #9](https://github.com/MSH4R1F/proposer/pull/9))
  - **Schema**: 13 tables + 15 enums; hand-written initial Alembic migration `0001_initial_schema.py`. Tables: `intake_sessions`, `disputes`, `predictions` + 3 children (`prediction_issues`, `prediction_reasoning_steps`, `prediction_citations`), `knowledge_graphs`/`kg_nodes`/`kg_edges` (composite `(case_id, node_id)` PK preserves polymorphic node identity), `mediations`/`mediation_messages`/`structured_offers`, `evidence_metadata`.
  - **Repositories**: 6 repos under `apps/api/src/db/repositories/` translate between Pydantic domain models and SQLAlchemy rows. JSONB payload carries the full Pydantic dump; projection columns serve indexed queries. Optimistic locking via `version` columns; row locks via `lock_for_prediction_cache`.
  - **Unit of Work**: `apps/api/src/db/uow.py` — request-scoped `UnitOfWork` async context manager exposing all six repos on one `AsyncSession`. Commits on clean exit, rolls back on exception. Routes reach services through `apps/api/src/dependencies.py` factories that inject the per-request UoW.
  - **Service rewrites**: `IntakeService`, `DisputeService`, `PredictionService`, `StorageService`, `MediationService` dropped JSON-file persistence. The four mediation atomicity hazards (`settle`, `escalate`, `accept_offer→settle`, `start_mediation`) and chat-start session+dispute create are each one transaction with provable rollback on second-write failure.
  - **Migration toolchain** under `scripts/migrations/`: `audit_json_stores`, `backfill_json_to_postgres` (`--dry-run`/`--commit`/`--verify`/`--archive-json`), `dump_postgres_to_json` (rollback insurance), `print_db_target` (cutover preflight), `check_model_alignment` (CI-enforced projection map).
  - **Operational**: `docker-compose.yml` (Postgres 16), `Makefile` targets (`db-up`/`db-down`/`db-reset`/`migrate`), GitHub Actions CI at `.github/workflows/ci.yml`, `/readyz` probe asserting Alembic head matches.
  - **Production safety**: `APIConfig` refuses `localhost` / `proposer-dev` / non-TLS DSNs in `production`. Backfill is fail-closed on validation errors, FK orphans, duplicate IDs, and projection drift.
  - **Real-data verification**: 331 JSON files (240 sessions / 42 predictions / 22 disputes / 16 KGs / 4 mediations / 7 dispute_predictions) backfilled and round-trip-verified with **0 mismatches**.
  - **Test count**: ~210 passing tests across `apps/api/tests/` (unit, repo, integration, atomicity, contract, legal-invariants) and `scripts/migrations/tests/`.
  - **Spec**: `docs/superpowers/specs/2026-04-29-postgres-migration-design.md`. **Plan**: `docs/superpowers/plans/2026-04-29-postgres-migration.md`.

- **Improved Invite Code Display & Prediction Blocking** - Better UX for multi-party disputes
  - **UI Changes**:
    - Moved invite code display from bottom input area to the right sidebar
    - Invite code no longer blocks the chat input textbox
    - Added compact invite code section with copy/share buttons in sidebar
    - Shows "Both Parties Connected" indicator when other party joins
  - **Prediction Engine Blocking**:
    - Added `is_ready_for_prediction` field to track when both parties have completed intake
    - Prediction button is now blocked until BOTH parties have completed their intake (not just joined)
    - Shows distinct messaging for: waiting for other party to join vs waiting for them to complete
    - Clear status indication: "Your Intake Complete!", "Waiting for Other Party", or "Both Parties Complete!"
  - **Backend Changes**:
    - Added `is_ready_for_prediction` to `DisputeInfo` API model
    - Now returns completion status based on dispute status (BOTH_COMPLETE or READY_FOR_MEDIATION)

- **Simplified Session Creation Flow** - Streamlined the role-setting process for better UX
  - **Backend Changes**:
    - `IntakeService.start_session()` now accepts optional `role` parameter
    - `IntakeAgent.start_conversation()` advances to BASIC_DETAILS when role is provided
    - Greeting generation now uses role-appropriate prompts when role is set at creation
  - **API Changes**:
    - `POST /chat/start` now directly creates session with role (single call instead of two)
    - Removed redundant intermediate `set_role()` call from start endpoint
    - `POST /chat/set-role` remains available for changing role mid-conversation
  - **Benefits**:
    - Reduced API calls from 2 to 1 for session creation
    - Cleaner code flow and better separation of concerns
    - First question is now role-appropriate immediately
    - Faster user experience with less latency

### Added

- **Comprehensive Debug Logging** - Enhanced structured logging throughout the FastAPI application
  - **Main Application** (`main.py`)
    - Environment configuration checks (API keys, directories)
    - Directory creation tracking
    - CORS configuration logging
    - Router registration logging
    - Health check endpoint logging
  - **Chat Router** (`routers/chat.py`)
    - Request/response logging for all endpoints (start, message, set-role, session, delete)
    - Message length and preview tracking
    - Stage transitions and completeness tracking
    - Session operations (create, retrieve, delete)
    - Role validation and setting
    - Error logging with error types
  - **Intake Service** (`services/intake_service.py`)
    - Service initialization with LLM configuration details
    - Session lifecycle tracking (create, store, load, save)
    - Message processing flow with intermediate steps
    - Role setting operations
    - Agent interactions and responses
    - Session persistence (memory vs disk)
    - Data validation and error tracking
  - **Evidence Router** (`routers/evidence.py`)
    - File upload requests with metadata
    - File type validation
    - Storage operations
    - Evidence listing and deletion
    - Extracted text and image description tracking
  - **Predictions Router** (`routers/predictions.py`)
    - Prediction generation requests
    - Case readiness checks
    - Prediction results with confidence and outcomes
    - Issue predictions and case analysis count
    - Prediction retrieval and listing
  - **Cases Router** (`routers/cases.py`)
    - Case retrieval with details (role, completeness, issues)
    - Full case file access
    - Case listing and deletion
  - **Configuration** (`config.py`)
    - Environment variable loading with validation
    - Directory creation
  - **Logging Format**: All logs use structured format with relevant context (session_id, case_id, error types, metrics)
  - **Logging Levels**: Debug for detailed flow, Info for important events, Warning for issues, Error for failures

### Changed

- **Frontend Redesign** - Complete CSS/styling overhaul for professional legal-tech aesthetic
  - **New Design System**
    - Custom color palette with deep navy primary and warm amber accents
    - DM Sans font for body text, JetBrains Mono for code/numbers
    - Sophisticated shadows (soft, glow effects) and rounded corners
    - Glass morphism effects and gradient backgrounds
  - **Enhanced Components**
    - Redesigned Cards with hover effects and gradient overlays
    - Improved Buttons with active states and smooth transitions
    - Better Input/Textarea styling with focus states
    - Animated Skeleton loading states with shimmer effect
  - **Homepage Improvements**
    - Hero section with radial gradients and dot patterns
    - Animated stats section with icons
    - Feature cards with color-coded icons and hover effects
    - Staggered entrance animations
  - **Chat Interface Polish**
    - Redesigned message bubbles with sender labels
    - Improved role selector with hover gradients
    - Better progress indicator with pulse animations
    - Enhanced completeness bar with gradient fill
  - **Prediction Page Enhancements**
    - Outcome display with confidence gauge and color-coding
    - Financial summary with icon-based layout
    - Strengths/Weaknesses cards with gradient top borders
    - Improved skeleton loading states
  - **Header/Footer Updates**
    - Logo with animated accent dot
    - Better navigation styling
    - Enhanced legal disclaimer card

### Added

- **Next.js Frontend** (`apps/web/`) - Complete web application for the mediation system
  - **Landing Page** - Hero section, feature cards, statistics, call-to-action
  - **Chat Interface** - 10-stage conversational intake with role selection
    - Role selector (Tenant/Landlord buttons)
    - Progress indicator showing intake stages
    - Completeness bar (0-100%)
    - Message bubbles with typing indicators
    - Auto-scroll and session persistence (localStorage)
  - **Prediction Display** - Full results page with transparent reasoning
    - Outcome display with confidence gauge
    - Settlement range and financial summary
    - Per-issue breakdown with individual predictions
    - Expandable reasoning trace with citations
    - Key strengths/weaknesses lists
    - Legal disclaimer prominently displayed
  - **Components** (60+ files)
    - 11 shadcn/ui base components (Button, Card, Progress, Badge, etc.)
    - 9 chat components (ChatContainer, MessageBubble, RoleSelector, etc.)
    - 12 prediction components (PredictionCard, ReasoningTrace, CitationCard, etc.)
    - 5 shared components (Header, Footer, LoadingSpinner, ErrorMessage)
  - **API Integration** - Full integration with FastAPI backend
    - Chat API (start, set-role, message, session)
    - Predictions API (generate, get)
  - **Tech Stack**: Next.js 14+, TypeScript, shadcn/ui, Tailwind CSS

- **LLM Orchestrator Package** (`packages/llm_orchestrator/`) - Conversational intake agents and prediction engine
  - **Core Data Models** (`models/`)
    - `case_file.py` - CaseFile with PropertyDetails, TenancyDetails, EvidenceItem, ClaimedAmount
    - `conversation.py` - ConversationState, Message, IntakeStage management
    - `prediction.py` - PredictionResult, ReasoningStep, Citation, IssuePrediction
  - **Claude Client** (`clients/claude_client.py`) - Anthropic API integration with fallback, retry, cost tracking
  - **Intake Agent** (`agents/intake_agent.py`) - 10-stage conversational intake with role detection
  - **Prediction Engine** (`agents/prediction_agent.py`) - RAG + LLM synthesis with cite-or-abstain rule
  - **Fact Extractor** (`extractors/fact_extractor.py`) - LLM-based structured fact extraction
  - **Evidence Processor** (`extractors/evidence_processor.py`) - PDF text extraction, image description
  - **Prompt Templates** (`prompts/`)
    - Separate tenant and landlord interview flows
    - Fact extraction prompts with confidence scoring
    - Prediction synthesis with JSON schema output
  - **CLI** (`cli.py`) - Interactive chat interface for testing intake flow

- **Knowledge Graph Builder** (`packages/kg_builder/`) - Structured case representation
  - **Node Types** (`models/nodes.py`) - Party, Property, Lease, Evidence, Event, Issue, ClaimedAmount
  - **Edge Types** (`models/edges.py`) - Evidence_Supports, Event_Before, Party_Claims, etc.
  - **KnowledgeGraph** (`models/graph.py`) - Graph container with path finding, node queries
  - **GraphBuilder** (`builders/graph_builder.py`) - CaseFile to KnowledgeGraph conversion
  - **Validators** (`builders/validators.py`) - Temporal logic, evidence chain validation
  - **JSON Storage** (`storage/json_store.py`) - File-based persistence (Neo4j-ready)

- **FastAPI Application** (`apps/api/`) - REST API for the mediation system
  - **Routers**
    - `/chat` - Conversational intake endpoints (start, message, session)
    - `/evidence` - File upload to Supabase Storage
    - `/predictions` - Outcome prediction generation
    - `/cases` - Case management
  - **Services**
    - `intake_service.py` - Session management, conversation orchestration
    - `prediction_service.py` - RAG + KG + LLM prediction pipeline
    - `storage_service.py` - Supabase/local file storage
  - OpenAPI documentation at `/docs`
  - Health check endpoint at `/health`

- **New Scripts**
  - `scripts/intake.py` - CLI runner for intake agent testing
  - `scripts/api.py` - FastAPI server runner

- **Root requirements.txt** - Consolidated dependencies for all packages

- **Comprehensive Test Suite** (`packages/rag_engine/tests/`) - 141 tests covering all RAG components
  - `conftest.py` - Shared fixtures: sample documents, chunks, mocks, golden dataset
  - `test_config.py` - Configuration and Pydantic data model validation (19 tests)
  - `test_text_cleaner.py` - PII redaction, encoding fixes, noise removal (21 tests)
  - `test_legal_chunker.py` - Document chunking, section detection, overlap (17 tests)
  - `test_bm25_index.py` - BM25 indexing, search, persistence, lite mode (23 tests)
  - `test_reranker.py` - Re-ranking, boosts (recency, region), issue detection (18 tests)
  - `test_hybrid_retriever.py` - Hybrid search, RRF fusion, scoring (14 tests)
  - `test_pipeline.py` - End-to-end pipeline, ingestion, retrieval, confidence (16 tests)
  - `test_retrieval_quality.py` - Golden dataset evaluation, calibration, cite-or-abstain (13 tests)
  - `pytest.ini` - Test configuration with markers (slow, integration, requires_api)

- **BM25 Index Rebuild Script** (`scripts/rebuild_bm25.py`) - Utility to rebuild BM25 index from ChromaDB
  - Extracts all documents from ChromaDB and reconstructs DocumentChunk objects
  - Supports both full and lite mode rebuilding
  - Useful for recovering from index corruption without re-ingesting PDFs

- **RAG Quality Test Script** (`scripts/test_rag_quality.py`) - Automated retrieval quality evaluation
  - Tests 5 sample queries with expected topics and case types
  - Calculates topic precision, case type precision, and confidence metrics
  - Compares hybrid search performance

- **Test Runner Script** (`scripts/run_tests.py`) - Convenient test execution
  - `--unit-only` - Run only unit tests (excludes integration)
  - `--coverage` - Generate coverage report
  - `--integration` - Include live system tests
  - `-k` - Filter tests by expression

### Fixed
- **Chat routing mismatch** - Fixed Next.js routing so chat sessions resolve under `/chat` as intended
  - Added proper routes at `app/(chat)/chat/page.tsx` and `app/(chat)/chat/[sessionId]/page.tsx`
  - Removed conflicting `app/(chat)/page.tsx` and `app/(chat)/[sessionId]/page.tsx` which mapped to `/` and `/:sessionId`
- **Chat session ID recycling** - Prevented repeated session creation (and rapid redirects between IDs) in dev
  - Added an in-flight guard in `ChatContainer` to avoid duplicate `startSession()` calls during StrictMode effect re-runs
- **Chat Session Synchronization** - Fixed critical bugs in frontend-backend chat integration
  - **Session Polling Bug**: Fixed multiple session IDs being created on each page visit
    - Root cause: `lastSessionIdRef` wasn't updated before redirect, causing re-initialization
    - Solution: Updated `ChatContainer.tsx` to set ref before `router.replace()`
  - **Message Restoration**: Fixed chat appearing empty when resuming sessions
    - Root cause: Backend didn't return messages in session endpoint; frontend didn't restore them
    - Solution: Added `messages` field to `GET /chat/session/{id}` response; updated `resumeSession()` hook
  - **Role Selection Sync**: Fixed role selector appearing incorrectly for existing sessions
    - Root cause: Only checking `case_file.user_role` which could be undefined
    - Solution: Also check if stage is past `greeting` to determine role selection state
  - **Next.js 15 Params**: Fixed async params handling in dynamic routes
    - Root cause: Next.js 15 changed params to Promises requiring `use()` hook
    - Solution: Updated `[sessionId]/page.tsx` to use `use(params)`

- **BM25 Index Corruption** - Fixed corrupted 84-byte BM25 index that caused division by zero errors
  - Root cause: Index was saved before any documents were added
  - Solution: Created rebuild script to regenerate from ChromaDB (43,776 chunks)

- **BM25 Lite Mode Metadata** - Fixed missing `year`, `region`, `case_type` fields in lite mode
  - Updated `bm25_index.py` to store and retrieve all metadata fields
  - Ensures DocumentChunk reconstruction works correctly after persistence

### Changed
- Updated Development Phases to mark "Comprehensive testing suite" as in progress

---

- **RAG Engine** (`packages/rag_engine/`) - Complete retrieval-augmented generation pipeline for tribunal case search
  - **PDF Extraction**: PyMuPDF-based text extraction from tribunal decision PDFs
  - **Text Cleaning**: PII redaction (postcodes, phones, emails), encoding normalization
  - **Legal Chunking**: Section-aware chunking (~500 tokens) that detects Background/Facts/Reasoning/Decision sections
  - **OpenAI Embeddings**: text-embedding-3-small integration with async batching, retry logic, cost tracking
  - **ChromaDB Vector Store**: Persistent storage with metadata filtering (year, region, case_type)
  - **BM25 Keyword Index**: rank-bm25 implementation for legal terminology matching
  - **Hybrid Retrieval**: Reciprocal Rank Fusion (RRF) combining semantic + keyword search
  - **Custom Reranker**: Domain-specific re-ranking by issue type, temporal relevance, region, evidence similarity
  - **Uncertainty Detection**: Confidence scoring with explicit "uncertain" flags for novel cases
  - **CLI Interface**: Commands for ingest, query, stats, and PDF extraction testing

- **BAILII Scraper** - Production-ready async Python scraper for UK First-tier Tribunal decisions
  - Scrapes Property Chamber cases from https://www.bailii.org/uk/cases/UKFTT/PC/
  - Downloads both HTML and PDF for each case
  - Keyword-based categorization (deposit, adjacent, other)
  - SQLite progress tracking with resume capability
  - Rate limiting (1 req/sec) with exponential backoff retries
  - CLI with flexible year selection (`--years`, `--year-range`)

### New Files
- `packages/rag_engine/` - RAG pipeline package (~2,400 lines of code)
  - `config.py` - Configuration and Pydantic data models (CaseDocument, DocumentChunk, RetrievalResult, QueryResult)
  - `pipeline.py` - Main RAG orchestrator with ingest/retrieve methods
  - `cli.py` - Click-based CLI with ingest, query, stats, clear commands
  - `extractors/pdf_extractor.py` - PyMuPDF text extraction
  - `extractors/text_cleaner.py` - PII redaction and text normalization
  - `chunking/legal_chunker.py` - Section-aware legal document chunking
  - `embeddings/base.py` - Abstract embedding interface (Pinecone-ready)
  - `embeddings/openai_embeddings.py` - OpenAI text-embedding-3-small implementation
  - `vectorstore/base.py` - Abstract vector store interface
  - `vectorstore/chroma_store.py` - ChromaDB implementation with metadata filtering
  - `retrieval/bm25_index.py` - BM25 keyword search index
  - `retrieval/hybrid_retriever.py` - RRF fusion of semantic + BM25
  - `retrieval/reranker.py` - Domain-specific re-ranking
  - `README.md` - Comprehensive documentation with architecture diagram
- `scripts/rag.py` - CLI runner script
- `scripts/scrapers/` - BAILII scraper package
  - `config.py` - Keywords, settings, rate limits
  - `models.py` - Pydantic data models for cases
  - `parsers.py` - HTML parsing for year index and case pages
  - `downloader.py` - Async HTTP client with retries
  - `progress.py` - SQLite progress tracking
  - `bailii_scraper.py` - Main CLI orchestrator
- `data/raw/bailii/` - Output directory structure (447 cases scraped)

### Technical Decisions
- **Hybrid Search**: Combines semantic embeddings with BM25 keyword search using Reciprocal Rank Fusion
- **text-embedding-3-small**: Chosen over large variant for 6.5x cost savings with minimal accuracy loss
- **ChromaDB**: Local development with abstract interface for future Pinecone migration
- **Section-aware chunking**: Preserves legal document structure (Background/Facts/Reasoning/Decision)
- **Domain reranking**: Weights issue type match (0.4), temporal relevance (0.2), region (0.1), evidence (0.2)

### Planned Features
- Knowledge Graph extraction from case facts
- Hybrid RAG + KG prediction engine
- Shadow mediator for real-time negotiation
- ZOPA (Zone of Possible Agreement) calculation
- Interactive intake chat interface
- Case dashboard with reasoning trace visualization

---

## [0.1.0] - 2024-12-24

### Added
- Initial project structure and repository setup
- Project documentation (README.md, CLAUDE.md, .cursorrules)
- Monorepo architecture with apps/ and packages/ structure
- Development guidelines and coding standards
- Legal safety and compliance guidelines
- .gitignore configuration for Python, Node.js, and sensitive data
- CHANGELOG.md for tracking project updates

### Project Structure
- `apps/api/` - FastAPI backend application
- `apps/web/` - Next.js 14 frontend application
- `apps/workers/` - Background workers for data processing
- `packages/rag-engine/` - RAG pipeline for case retrieval
- `packages/kg-builder/` - Knowledge Graph construction
- `packages/llm-orchestrator/` - LLM agent coordination
- `packages/legal-db/` - Database schemas and migrations
- `packages/shared/` - Shared utilities and types
- `data/` - Data storage (raw, processed, embeddings, test cases)
- `docs/` - Additional documentation
- `scripts/` - Utility scripts for development

### Documentation
- Comprehensive README with project overview and architecture
- CLAUDE.md with technical specifications
- .cursorrules with development guidelines and legal compliance rules

---

## Version History

### Version Numbering Guide
- **MAJOR** version for incompatible API changes or significant architectural shifts
- **MINOR** version for new features in a backward-compatible manner
- **PATCH** version for backward-compatible bug fixes

### Categories
- **Added** - New features
- **Changed** - Changes in existing functionality
- **Deprecated** - Soon-to-be removed features
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Vulnerability fixes

---

## Development Phases

### Phase 1: Foundation (Current)
- [ ] Complete project setup and infrastructure
- [ ] Set up development environment
- [ ] Initialize databases (PostgreSQL, ChromaDB, Neo4j)
- [ ] Configure authentication (Supabase Auth)

### Phase 2: Data Pipeline (Sprint 1-2)
- [x] Implement BAILII scraper for tribunal decisions
- [x] Implement PDF parsing and text extraction (PyMuPDF)
- [x] Build RAG pipeline with ChromaDB (Pinecone-ready interface)
- [x] Implement hybrid search (BM25 + semantic with RRF fusion)
- [x] Add PII redaction system (postcodes, phones, emails)
- [ ] Create basic prediction engine

### Phase 3: Knowledge Graph (Sprint 3-4)
- [ ] Design and implement KG ontology (Neo4j)
- [ ] Build NLP-based fact extraction
- [ ] Implement constraint validation
- [ ] Integrate hybrid RAG + KG prediction
- [ ] Set up evaluation framework

### Phase 4: Frontend & UX (Sprint 5-6)
- [ ] Build authentication flows
- [ ] Create case dashboard
- [x] Implement intake chat interface
- [x] Design reasoning trace visualization
- [ ] Add case status tracking
- [x] Build landing page with CTA
- [x] Create prediction results page

### Phase 5: Mediation Features (Sprint 7-8)
- [ ] Implement shadow mediator agent
- [ ] Build ZOPA calculation engine
- [ ] Create real-time negotiation interface
- [ ] Add nudge generation system
- [ ] Implement settlement tracking

### Phase 6: Production Readiness
- [x] Comprehensive testing suite (141 tests for RAG engine)
- [ ] Security audit and penetration testing
- [ ] Performance optimization
- [ ] Legal compliance review
- [ ] User acceptance testing
- [ ] Deployment to Railway

---

## Notes for Developers

### How to Update This Changelog

1. **During Development**: Add unreleased changes under `[Unreleased]` section
2. **On Release**: 
   - Move unreleased changes to a new version section
   - Update the version number and date
   - Add a link to the version comparison at the bottom
3. **Always Include**:
   - Date in YYYY-MM-DD format
   - Clear description of what changed
   - Migration notes if breaking changes
   - Security notes if relevant

### Example Entry
```markdown
## [1.2.0] - 2024-03-15

### Added
- New prediction confidence calibration using Brier Score
- Support for Housing Ombudsman case data in RAG pipeline

### Changed
- Improved LLM prompt for better citation accuracy (breaking: update prompts in config)

### Fixed
- Knowledge Graph extraction failing on cases with missing dates (#42)
- Frontend crash when displaying cases with no evidence (#45)

### Security
- Updated dependencies to patch CVE-2024-12345 in FastAPI
```

---

## Contact & Contributions

For questions about changes or to report issues:
- Check the [README.md](./README.md) for project overview
- Review [CLAUDE.md](./CLAUDE.md) for technical details
- Follow the development guidelines in [.cursorrules](./.cursorrules)

---

**Remember**: This changelog tracks **user-facing changes** and **significant technical milestones**. For detailed commit history, use `git log`.
