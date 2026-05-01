"""Cross-pack cite-or-abstain scaffold.

A claim must be backed by at least one of:

- a user fact recorded on the case file
- uploaded evidence
- a retrieved legal source (case decision, ombudsman determination, statute, guidance)
- a deterministic calculator trace
- a statute / guidance reference

If no such backing exists, the prompt MUST abstain rather than guess. Statutory
limit claims (e.g., 1x-3x deposit penalty, basic-award weekly cap) MUST prefer
calculator-trace citations over similar-case citations.
"""

from __future__ import annotations

CITE_OR_ABSTAIN_VERSION = "1.1.0"


_CITE_OR_ABSTAIN_TEMPLATE = """CITE-OR-ABSTAIN POLICY:
- Every factual or legal claim must be supported by at least one source from the
  following allowed citation kinds for THIS forum: {allowed_citation_kinds}.
- If no source from this allowlist supports a claim, abstain. Set the outcome
  to "uncertain" and explain the gap.
- For statutory limits or formulaic figures (e.g., 1x-3x deposit, basic-award
  weekly cap), prefer the deterministic_calculator_trace citation kind over
  similar-case citations whenever a calculator trace is available.
- Do NOT invent citations. Only reference items provided in the context.
- The forum-specific citation label is: "{citation_label}". Use that label when
  introducing each citation in narrative reasoning.
"""


def build_cite_or_abstain_block(
    allowed_citation_kinds: list[str],
    citation_label: str,
) -> str:
    kinds = ", ".join(sorted(allowed_citation_kinds)) or "(none configured)"
    return _CITE_OR_ABSTAIN_TEMPLATE.format(
        allowed_citation_kinds=kinds,
        citation_label=citation_label or "(unspecified citation label)",
    )
