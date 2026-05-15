# Employment Tribunal corpus — licence and attribution

## Source

UK Employment Tribunal decisions are published at
[`https://www.gov.uk/employment-tribunal-decisions`](https://www.gov.uk/employment-tribunal-decisions).

## Licence

The GOV.UK Employment Tribunal decisions corpus is published under the
**Open Government Licence v3.0** unless a specific page states otherwise.

- Full licence text: <https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>
- Crown copyright statement: <https://www.gov.uk/help/terms-conditions>

## Attribution string

Any product surface that quotes or cites material from this corpus must
include the following attribution (verbatim) at point of use:

> Contains public sector information licensed under the Open Government
> Licence v3.0 (<https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>).

The same string is exported as `OGL_V3_ATTRIBUTION` from
`scripts.scrapers.employment_tribunal.__init__` and is asserted by the
test suite.

## Per-page observed licence

Each ingested document persists the observed licence string in
`SourceMetadata.source_license` (and in
`SourceDocument.extra.source_license_observed` for QA). Possible values:

| Value | Meaning |
|---|---|
| `OGL-3.0` | Page footer explicitly named Open Government Licence v3.0. |
| `OGL-3.0-inferred` | Page footer was silent; we recorded the GOV.UK default but flagged the inference. |
| `OGL-unversioned` | Page named the Open Government Licence without a version. |
| `crown_copyright_check` | Page named Crown Copyright but no OGL — needs human review before redistribution. |

## PII / redaction

Raw public source pages may contain claimant PII (postcodes, phone
numbers, email addresses, NI numbers, bank details). The model-facing
`SourceDocument.raw_text` written into
`data/raw/employment/decisions/<case_ref>/source_document.json` is
redacted at ingestion via
[`scripts.scrapers.employment_tribunal.to_source_document.redact_model_facing_text`](../../../scripts/scrapers/employment_tribunal/to_source_document.py).
Redaction stats are persisted on `SourceDocument.extra.redaction_stats`
for the SHA-65b pilot PII audit.

## Reuse

Republishing snippets externally is only permitted when:

1. `source_license` is `OGL-3.0` (not the `-inferred` variant alone — that
   requires a human spot-check first), and
2. The attribution string above is included at point of use, and
3. PII redaction has passed the SHA-65b regression sweep.

The SHA-145 / SHA-65a scaffold is research-stage; do not surface this
corpus on user-facing product paths until SHA-65b and SHA-65d gates have
landed.
