"""SHA-126: GOV.UK Property Tribunal RRO scraper.

A pilot-scale scraper for First-tier Tribunal Property Chamber Rent
Repayment Order decisions published on GOV.UK under the
``residential_property_tribunal_decision`` content type.

Audit gate (D4): RRO ONLY. Leasehold service charges, ground rent,
Tenant Fees Act, park homes, building safety, and broad regulatory
appeals are explicitly out of scope and routed to ``excluded.jsonl``.
"""

__version__ = "0.1.0"
