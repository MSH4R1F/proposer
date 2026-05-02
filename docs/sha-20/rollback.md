# SHA-20 Phase 8 — Rollback playbook

This file is the canonical reference for rolling back any change introduced
by Phase 8 (feature flags, launch gates, trace tags). It complements the
gate-specific rollback section in
[`docs/eval/gates.md`](../eval/gates.md#rollback-paths) — read both before
acting.

The Phase 8 rule of thumb: **prefer additive rollback** (publish a new
artifact pointing at the previous good state) over destructive rollback
(dropping columns, deleting collections). Hot rollbacks must be
reversible without a redeploy.

## Five rollback paths

### 1. Domain rollback

**Symptom:** A new domain is misbehaving in production / beta and we need
to take it offline immediately.

**Action:** Remove the domain id from `ENABLED_DOMAINS` and redeploy.

The domain stays loadable from the registry (its YAML, ontology and
prompt pack still ship), but `resolve_domain_runtime` now reports
`gate_status=disabled` for any request that targets it. Existing
prediction rows are preserved; reads still work because the projection
layer doesn't depend on enabled-domain status.

```
ENABLED_DOMAINS=housing.deposit.v1,housing.repairs_social.v1   # remove employment.unfair_dismissal.v1
```

### 2. Gate rollback

**Symptom:** A freshly published gate artifact is wrong (bad metric, bad
reviewer set, bad signing key once Phase 8.5 lands).

**Action:** Restore the previous artifact JSON from git history at
`data/eval_artifacts/domain_gates/{domain_id}.json`. The verifier
recomputes `artifact_hash` and rejects anything that doesn't match —
mismatched hashes fail closed.

If no good previous artifact exists, simply DELETE the artifact file:
`DomainGateChecker` will return `gate_missing` and (with strict gates
on) the runtime refuses the domain.

### 3. Prompt-pack / ontology rollback

**Symptom:** A change to a prompt pack or ontology produces unsafe
output. We don't want to wait for the full eval cycle.

**Action:** Publish a new gate artifact whose `prompt_pack_hash` /
`ontology_hash` points at the previous good values. The runtime cache
key incorporates these hashes, so cached predictions invalidate
automatically; live requests pick up the previous behaviour on the next
turn.

The prompt-pack file itself does NOT need to be reverted in git for the
rollback to take effect — the gate artifact is the source of truth for
"what's currently allowed in production."

### 4. Corpus rollback

**Symptom:** A new corpus version (e.g. an updated BAILII scrape) has
poisoned retrieval quality.

**Action:** Publish a new gate artifact pointing at the previous
`corpus_version` and `namespace_id`. Old Chroma collections are retained
on disk by default — Phase 4's `cleanup-corpus` CLI only deletes when
invoked with `--apply`, and it preserves any version still referenced
by persisted predictions.

If the cleanup CLI was already run with `--apply`, restore from object
storage (S3/Drive) before publishing the new artifact.

### 5. DB rollback

**Symptom:** A migration shipped along with a Phase 8 feature is
implicated in an outage.

**Action:** **Do not drop the additive domain columns** as a hot
rollback. The columns (`domain_id`, `domain_version`, `prompt_pack_hash`,
`ontology_hash`, `corpus_version`, `domain_spec_hash`, `routing_metadata`,
`matter_types`) are written nullable and back-fill in place. A hot
rollback should:

1. Revert the application code to a version that does not require the
   columns (write paths must accept `NULL`).
2. Leave the columns alone in Postgres; they are read by repositories
   defensively (see `_extract_repro_hashes`).

A clean migration-down can happen later, in maintenance, after the
incident is closed.

## What NOT to roll back as a hot fix

- **Trace-tag schema:** `TraceSummary.metadata` is additive. New tags
  appearing in the trace store are harmless to consumers that don't
  read them. Removing tags retroactively is a destructive operation;
  don't.
- **Employment trace scrubbing:** the regex-based scrubber in
  `packages/llm_orchestrator/agent_loop/trace.py:_scrub_employment_trace_text`
  is conservative by design. If it over-masks, fix forward — never
  ship a path that defaults to pass-through. The Phase 11 plan
  upgrades this to a real redaction module.

## Sequencing for a multi-domain incident

If multiple paths are implicated:

1. Domain rollback first (path 1) to stop the bleeding.
2. Then gate / prompt / ontology rollback (paths 2-4) once you have
   bandwidth to publish a new artifact.
3. DB-level work (path 5) goes last and is rarely a hot path.

## Cross-references

- [`docs/eval/gates.md`](../eval/gates.md) — gate-artifact lifecycle.
- [`docs/eval/leakage_controls.md`](../eval/leakage_controls.md) — runtime
  leakage controls and how they interact with corpus rollback.
- [`docs/superpowers/audits/2026-05-01-domain-corpus-boundary-audit.md`](../superpowers/audits/2026-05-01-domain-corpus-boundary-audit.md)
  — audit decisions D2 (deposit fail-closed), D5 (employment first
  slice), D6 (deposit non-protection unsupported) that Phase 8 enforces.
