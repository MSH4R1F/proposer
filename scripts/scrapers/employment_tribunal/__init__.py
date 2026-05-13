"""SHA-145 / SHA-65a GOV.UK Employment Tribunal scraper package.

Scrapes a polite, bounded sample of UK Employment Tribunal decisions from
``https://www.gov.uk/employment-tribunal-decisions``, applies a two-stage
filter (Stage 1 GOV.UK category, Stage 2 merits-quality), redacts model-facing
PII, and emits ``SourceDocument`` records keyed to the
``employment_unfair_dismissal_v1`` retrieval namespace.

Domain ID note (spec §3.1): this scraper uses the existing legacy domain ID
``employment.unfair_dismissal.v1`` as the compatibility identifier. The
namespaced ID ``employment.et.unfair_dismissal.v1`` will be introduced
via a separate v2/domain-pack migration; do not rename in this PR.

Live scraping lives in SHA-65b (SHA-146). This module only provides the
parsers, filters, downloader, persistence layer, and CLI scaffold needed
to run a pilot — no network calls are made by the test suite.

Output paths (under ``data/raw/employment/``) and ingestion contract follow
the SHA-20 Phase 4 ``SourceMetadata`` shape.
"""

PARSER_VERSION = "employment-tribunal-0.1.0"

# OGL v3.0 attribution. Persist this string on every SourceMetadata so the
# citation mapper / disclaimers can credit GOV.UK at point of use. The full
# attribution text lives in ``data/raw/employment/LICENCE.md``.
#
# Note: per spec §5.1, this is the *default*. The scraper must persist the
# observed licence; if a particular GOV.UK page footer states otherwise the
# parser is expected to override this value at ingestion time. Today the
# GOV.UK Employment Tribunal corpus is uniformly OGL v3.0.
OGL_V3_LICENCE_ID = "OGL-3.0"
OGL_V3_ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government "
    "Licence v3.0 (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)."
)

__all__ = [
    "PARSER_VERSION",
    "OGL_V3_LICENCE_ID",
    "OGL_V3_ATTRIBUTION",
]
