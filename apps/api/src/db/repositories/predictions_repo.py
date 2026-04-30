from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import (
    PredictionRow, PredictionIssueRow, PredictionReasoningStepRow,
    PredictionCitationRow,
)
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult


class PredictionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, p: PredictionResult) -> None:
        payload = p.model_dump(mode="json")
        rng = p.predicted_settlement_range or (None, None)
        values = dict(
            prediction_id=p.prediction_id,
            case_id=p.case_id,
            created_at=p.timestamp,
            overall_outcome=p.overall_outcome.value,
            overall_confidence=float(p.overall_confidence),
            range_lo=rng[0], range_hi=rng[1],
            pipeline_version=getattr(p, "pipeline_version", None),
            model_version=getattr(p, "model_version", None),
            retrieval_quality=payload.get("retrieval_quality"),
            rag_confidence=payload.get("rag_confidence"),
            pipeline_metadata=payload.get("pipeline_metadata"),
            citation_verification=payload.get("citation_verification"),
            metadata_=payload.get("metadata"),
            payload=payload,
        )
        stmt = pg_insert(PredictionRow).values(**values)
        # Build the upsert set_ using the actual column names (not Python attr aliases).
        # "metadata_" is the Python attr for the "metadata" column; excluded uses column names.
        col_name_map = {"metadata_": "metadata"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[PredictionRow.prediction_id],
            set_={
                col_name_map.get(k, k): stmt.excluded[col_name_map.get(k, k)]
                for k in values if k != "prediction_id"
            },
        )
        await self._s.execute(stmt)

        await self._s.execute(
            delete(PredictionIssueRow).where(PredictionIssueRow.prediction_id == p.prediction_id)
        )
        await self._s.execute(
            delete(PredictionReasoningStepRow).where(
                PredictionReasoningStepRow.prediction_id == p.prediction_id
            )
        )
        await self._s.execute(
            delete(PredictionCitationRow).where(
                PredictionCitationRow.prediction_id == p.prediction_id
            )
        )

        for i, issue in enumerate(p.issue_predictions):
            ip = issue.model_dump(mode="json")
            ar = issue.amount_range or (None, None)
            self._s.add(PredictionIssueRow(
                prediction_id=p.prediction_id,
                ordinal=i,
                issue_type=issue.issue_type.value,
                issue_description=issue.issue_description,
                outcome=issue.outcome.value,
                raw_confidence=float(issue.raw_confidence),
                calibrated_confidence=ip.get("calibrated_confidence"),
                predicted_amount=issue.predicted_amount,
                amount_range_lo=ar[0], amount_range_hi=ar[1],
                reasoning=issue.reasoning,
                key_factors=ip.get("key_factors"),
                supporting_cases=ip.get("supporting_cases"),
                counterfactuals=ip.get("counterfactuals"),
                evidence_strength=(issue.evidence_strength.value
                                   if issue.evidence_strength else None),
                data_completeness_impact=ip.get("data_completeness_impact"),
                payload=ip,
            ))
            for j, c in enumerate(issue.supporting_cases or []):
                cd = c.model_dump(mode="json")
                self._s.add(PredictionCitationRow(
                    prediction_id=p.prediction_id, reasoning_step_id=None,
                    issue_ordinal=i, citation_source="issue_supporting_case", ordinal=j,
                    case_reference=c.case_reference, year=c.year, region=c.region,
                    paragraph=c.paragraph, quote=c.quote, relevance=c.relevance,
                    similarity_score=c.similarity_score, verified=c.verified,
                    payload=cd,
                ))

        for i, step in enumerate(p.reasoning_trace):
            sd = step.model_dump(mode="json")
            row = PredictionReasoningStepRow(
                prediction_id=p.prediction_id, ordinal=i,
                step_number=step.step_number, category=step.category,
                title=step.title, content=step.content, confidence=step.confidence,
                payload=sd,
            )
            self._s.add(row)
            await self._s.flush()
            for j, c in enumerate(step.citations or []):
                cd = c.model_dump(mode="json")
                self._s.add(PredictionCitationRow(
                    prediction_id=p.prediction_id, reasoning_step_id=row.id,
                    citation_source="reasoning", ordinal=j,
                    case_reference=c.case_reference, year=c.year, region=c.region,
                    paragraph=c.paragraph, quote=c.quote, relevance=c.relevance,
                    similarity_score=c.similarity_score, verified=c.verified,
                    payload=cd,
                ))

        verified = (payload.get("citation_verification") or {}).get("verified_citations") or []
        for j, vc in enumerate(verified):
            self._s.add(PredictionCitationRow(
                prediction_id=p.prediction_id, reasoning_step_id=None, issue_ordinal=None,
                citation_source="verified", ordinal=j,
                case_reference=vc.get("case_reference"), year=vc.get("year"),
                region=vc.get("region"), paragraph=vc.get("paragraph"),
                quote=vc.get("quote"), relevance=vc.get("relevance"),
                similarity_score=vc.get("similarity_score"),
                verified=vc.get("verified", True),
                payload=vc,
            ))
        removed = (payload.get("citation_verification") or {}).get("removed_citations") or []
        for j, rc in enumerate(removed):
            self._s.add(PredictionCitationRow(
                prediction_id=p.prediction_id, reasoning_step_id=None, issue_ordinal=None,
                citation_source="removed", ordinal=j,
                case_reference=rc.get("case_reference"), year=rc.get("year"),
                region=rc.get("region"), paragraph=rc.get("paragraph"),
                quote=rc.get("quote"), relevance=rc.get("relevance"),
                similarity_score=rc.get("similarity_score"),
                verified=rc.get("verified", False),
                payload=rc,
            ))

    async def get(self, prediction_id: str) -> Optional[PredictionResult]:
        row = await self._s.get(PredictionRow, prediction_id)
        return PredictionResult.model_validate(row.payload) if row else None

    async def get_by_case_id(self, case_id: str) -> list[PredictionResult]:
        result = await self._s.execute(
            select(PredictionRow).where(PredictionRow.case_id == case_id)
        )
        return [PredictionResult.model_validate(r.payload) for r in result.scalars()]

    async def projection_mismatches(self, prediction_id: str) -> list[str]:
        """Return projection mismatches against the canonical prediction payload."""
        row = await self._s.get(PredictionRow, prediction_id)
        if row is None:
            return ["missing_prediction"]
        prediction = PredictionResult.model_validate(row.payload)
        mismatches: list[str] = []

        issues_q = await self._s.execute(
            select(PredictionIssueRow)
            .where(PredictionIssueRow.prediction_id == prediction_id)
            .order_by(PredictionIssueRow.ordinal)
        )
        issue_rows = list(issues_q.scalars())
        expected_issues = [i.model_dump(mode="json") for i in prediction.issue_predictions]
        if [r.payload for r in issue_rows] != expected_issues:
            mismatches.append("prediction_issues")

        steps_q = await self._s.execute(
            select(PredictionReasoningStepRow)
            .where(PredictionReasoningStepRow.prediction_id == prediction_id)
            .order_by(PredictionReasoningStepRow.ordinal)
        )
        step_rows = list(steps_q.scalars())
        step_ordinal_by_id = {r.id: r.ordinal for r in step_rows}
        expected_steps = [s.model_dump(mode="json") for s in prediction.reasoning_trace]
        if [r.payload for r in step_rows] != expected_steps:
            mismatches.append("prediction_reasoning_steps")

        citations_q = await self._s.execute(
            select(PredictionCitationRow)
            .where(PredictionCitationRow.prediction_id == prediction_id)
            .order_by(
                PredictionCitationRow.citation_source,
                PredictionCitationRow.issue_ordinal,
                PredictionCitationRow.ordinal,
            )
        )
        citation_rows = list(citations_q.scalars())
        expected: list[tuple[str, Optional[int], int, dict]] = []
        for i, issue in enumerate(prediction.issue_predictions):
            for j, citation in enumerate(issue.supporting_cases or []):
                expected.append((
                    "issue_supporting_case",
                    i,
                    j,
                    citation.model_dump(mode="json"),
                ))
        for i, step in enumerate(prediction.reasoning_trace):
            for j, citation in enumerate(step.citations or []):
                expected.append(("reasoning", i, j, citation.model_dump(mode="json")))
        verification = prediction.citation_verification
        if verification is not None:
            for j, citation in enumerate(verification.verified_citations or []):
                expected.append(("verified", None, j, citation.model_dump(mode="json")))
            for j, citation in enumerate(verification.removed_citations or []):
                expected.append(("removed", None, j, citation.model_dump(mode="json")))
        actual = [
            (
                r.citation_source,
                step_ordinal_by_id.get(r.reasoning_step_id)
                if r.citation_source == "reasoning"
                else r.issue_ordinal,
                r.ordinal,
                r.payload,
            )
            for r in citation_rows
        ]
        if sorted(actual, key=lambda x: (x[0], x[1] if x[1] is not None else -1, x[2])) != sorted(
            expected, key=lambda x: (x[0], x[1] if x[1] is not None else -1, x[2])
        ):
            mismatches.append("prediction_citations")
        return mismatches

    async def delete(self, prediction_id: str) -> None:
        row = await self._s.get(PredictionRow, prediction_id)
        if row:
            await self._s.delete(row)
