# GOV.UK Property Tribunal Decisions Source Rights

## Scope

This folder is for a bounded research pilot of GOV.UK First-tier
Tribunal Property Chamber Rent Repayment Order decisions used by
Proposer's `housing.property_chamber.rro.v1` retrieval namespace.

## Licence Status

GOV.UK content is generally available under the Open Government Licence
3.0 unless a page states otherwise. This scraper records:

```text
OGL-3.0
```

on `SourceMetadata.source_license` for GOV.UK Property Tribunal RRO
decisions.

## Operational Constraints

Respect GOV.UK `robots.txt` and keep the pilot crawl bounded and polite.
The default scraper configuration uses a small `max_keep`, a page cap,
and a one-request-per-second throttle.

Do not assume every linked attachment has identical reuse terms. If a
decision page or attachment carries a separate rights notice, that notice
takes precedence and this file should be updated before ingestion.

## Attribution

Source publisher: GOV.UK.

Canonical pages should be linked through the source URL captured in
`SourceMetadata.source_url`.

When material is surfaced outside internal evaluation, include GOV.UK
attribution and the OGL-3.0 licence label where appropriate.
