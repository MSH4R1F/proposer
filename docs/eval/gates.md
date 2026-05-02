# Domain Launch Gates

> **Status**: SHA-20 Phase 7 (local MVP). Cryptographic Ed25519 signing
> is deferred to Phase 8.5; the local gate validates everything *except*
> signature bytes today.

## What is a `DomainGateArtifact`?

A `DomainGateArtifact` is an immutable on-disk JSON record at
`data/eval_artifacts/domain_gates/{domain_id}.json` that asserts a given
`(domain_id, stage)` pair has passed evaluation against a known gold set
on a known git revision.

The runtime gate refuses to serve a domain whose artifact is missing,
stale (mismatched `git_sha`), below threshold, or — at production/beta
stage — missing reviewer fields. This is the **fail-closed** primitive
the launch checklist depends on (audit decision D2).

The model lives in [`packages/eval/gates.py`](../../packages/eval/gates.py).

## Field reference

See [`DomainGateArtifact`](../../packages/eval/gates.py) for the
authoritative pydantic model. Required fields:

| Field | Type | Notes |
| --- | --- | --- |
| `domain_id` | string | e.g. `housing.deposit.v1` |
| `stage_requested` | `production` \| `beta` \| `research` | runtime gate is fail-closed if missing |
| `git_sha` | hex string | full commit; staleness gate compares against current `HEAD` |
| `corpus_version` | string | corpus version the gold set was annotated against |
| `gold_set_path` | path | must exist on disk for production gates (audit D2) |
| `n_cases` | int | for `housing.deposit.v1` production: must be >= 50 (audit D2) |
| `metrics` | dict | `accuracy`, `brier_score_max`, `hallucination_rate`, `citation_validity`, `abstention_precision` etc. |
| `prompt_pack_hash` | sha256 hex | from `llm_orchestrator.prompts.packs.hash_prompt_pack` |
| `ontology_hash` | sha256 hex | from `kg_builder.ontology.registry.hash_ontology_spec` |
| `domain_spec_hash` | sha256 hex | from `domain_core.hashing.hash_domain_spec` |
| `verifier_hash` | sha256 hex | sha256 of `llm_orchestrator/pipeline/citation_verifier.py` bytes |
| `reviewer_roles` | list[str] | non-empty for production/beta |
| `approved_by` | list[str] | non-empty for production/beta |
| `approved_at` | ISO-8601 datetime | wall-clock at sign-off |
| `artifact_hash` | sha256 hex | canonical-JSON SHA-256 of all *other* fields |
| `signature` | optional string | Phase 8.5 Ed25519 signature over `artifact_hash` |
| `signing_key_id` | optional string | key id; verified against the registered public-key map |
| `notes` | optional string | reviewer free-form |

## Hashing & signing policy

`artifact_hash` is the SHA-256 of the canonical-JSON encoding of every
field **except** `signature`, `signing_key_id`, and `artifact_hash`
itself. Canonical JSON sorts keys recursively, uses `(",", ":")`
separators, and forces ASCII. This makes the hash:

- **stable** across machines, CWDs, and key-insertion order;
- **independent of signing**: adding a signature is a pure wrapper.

A `signature` is intended to be an Ed25519 signature over
`artifact_hash`. Public keys live in
`packages/domain_core/keys/launch_gate_public_keys.json`. Private keys
must never be committed.

## Local MVP vs. production / beta

| Stage | Reviewer fields | Signature |
| --- | --- | --- |
| `research` | optional | optional |
| `beta` | required | warned today; **required** at Phase 8.5 |
| `production` | required | warned today; **required** at Phase 8.5 |

For the local MVP, `verify_gate_artifact` accepts `signature=None` and
emits a warning rather than failing. This is gated by the
`# TODO Phase 8.5` markers in `packages/eval/gates.py`.

The audit-D2 hard rule remains active regardless of stage:
`housing.deposit.v1` at `production` will refuse if
`data/gold_standard/housing_v1.jsonl` is missing on disk **or** if
`n_cases < 50`.

## Rollback paths

If a gate verification fails, do **not** disable the gate. Instead:

1. **Stage rollback** — flip the domain spec's `stage` to `research`
   (or `disabled`) and redeploy. The domain is still loadable; the
   runtime gate refuses production traffic.
2. **Artifact rollback** — restore the previous artifact JSON from git
   history and verify with the previous `git_sha`. The verifier
   compares hashes; mismatch fails closed.
3. **Gold-set rollback** — if the gold file was lost or corrupted,
   audit-D2 fail-closed activates automatically: production verify
   exits non-zero, runtime denies the domain. Restore the file before
   re-issuing an artifact.

See [`docs/eval/decision-log.md`](decision-log.md) for the audit-D2
context and the rationale for fail-closed rather than soft-failing.

## CLI

```bash
PYTHONPATH=packages python -m eval.gates verify \
    --domain housing.deposit.v1 \
    --stage production
```

Exits 0 on pass, 1 on any verification failure (including missing
artifact). Output is structured JSON listing `reasons` and `warnings`.

To build an artifact:

```bash
PYTHONPATH=packages python scripts/eval/build_domain_gate.py \
    --domain housing.deposit.v1 \
    --stage research \
    --metrics-json /tmp/metrics.json \
    --reviewer-roles housing_legal,product_safety \
    --approved-by reviewer1@example.com \
    --out data/eval_artifacts/domain_gates/housing.deposit.v1.json
```

`--sign` is reserved for Phase 8.5 Ed25519 wiring; it raises today.

## Public-key location

`packages/domain_core/keys/launch_gate_public_keys.json` holds the
registry of `signing_key_id -> public_key` pairs. The verifier reads
this map; if a `signature` is present, the `signing_key_id` MUST be
known here. Phase 8.5 will add the actual byte-level Ed25519 check.
