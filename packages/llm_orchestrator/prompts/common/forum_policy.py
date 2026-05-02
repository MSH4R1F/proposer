"""Forum-specific framing block used by every prompt pack.

Composes the ``ForumProfile`` fields into instruction text:

- The output framing string anchors the language model to forum-correct
  vocabulary (e.g., "complaint outcome analysis" for the Housing Ombudsman,
  not "court damages").
- Prohibited phrases tell the model what NEVER to emit. The deterministic
  ``ForumPolicyVerifier`` enforces these; this block only informs the model.
- Source-kind allowlists prevent the model from citing, e.g., a county-court
  damages case in a deposit-scheme adjudication context.
"""

from __future__ import annotations

FORUM_POLICY_VERSION = "1.0.0"


_FORUM_POLICY_TEMPLATE = """FORUM POLICY (this prompt is bound to a specific forum):
- Forum: {forum}
- Output framing: {output_framing}
- Citation label to use in narrative: "{citation_label}"
- Allowed source kinds for this forum: {source_kinds}

You MUST NOT use any of the following phrases anywhere in your output:
{prohibited_phrases}

Stay strictly inside the matter types this forum handles:
- Allowed matter types: {matter_types}
- If the case appears to fall outside these matter types, set the outcome to
  "uncertain" and explain that the matter is outside this forum's scope.
"""


def build_forum_policy_block(
    *,
    forum: str,
    output_framing: str,
    citation_label: str,
    source_kinds: list[str],
    prohibited_phrases: list[str],
    matter_types: list[str],
) -> str:
    if prohibited_phrases:
        prohibited_rendered = "\n".join(f"  - \"{p}\"" for p in prohibited_phrases)
    else:
        prohibited_rendered = "  - (none configured)"
    return _FORUM_POLICY_TEMPLATE.format(
        forum=forum,
        output_framing=output_framing or "(unspecified)",
        citation_label=citation_label or "(unspecified)",
        source_kinds=", ".join(sorted(source_kinds)) or "(none configured)",
        prohibited_phrases=prohibited_rendered,
        matter_types=", ".join(sorted(matter_types)) or "(none configured)",
    )
