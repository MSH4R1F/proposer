"""
Prediction service.

Orchestrates prediction generation with RAG integration.
Supports two-party dispute merging: when both tenant and landlord
have submitted for the same dispute, their CaseFiles are merged
into one and a single shared prediction is generated.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from llm_orchestrator.config import LLMConfig
from llm_orchestrator.clients.claude_client import ClaudeClient
from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2
from llm_orchestrator.models.prediction import PredictionResult
from llm_orchestrator.models.case_file import CaseFile, merge_case_files

from kg_builder.builders.graph_builder import GraphBuilder
from kg_builder.storage.json_store import JSONGraphStore

from apps.api.src.config import config
from apps.api.src.services.intake_service import get_intake_service

logger = structlog.get_logger()

# Global service instance
_prediction_service: Optional["PredictionService"] = None


class PredictionService:
    """
    Service for generating outcome predictions.

    Integrates RAG retrieval, knowledge graph, and LLM synthesis.
    Supports two-party disputes: merges both parties' CaseFiles and
    generates a single shared prediction cached by dispute_id.
    """

    def __init__(self):
        """Initialize the prediction service."""
        # Initialize components
        llm_config = LLMConfig.from_env()
        self.llm_client = ClaudeClient(api_key=llm_config.anthropic_api_key)

        # Prediction engine V2 (RAG pipeline loaded lazily)
        self.prediction_engine = PredictionEngineV2(
            llm_client=self.llm_client,
            rag_pipeline=None,  # Will be set when needed
        )

        # Knowledge graph
        self.graph_builder = GraphBuilder()
        self.kg_store = JSONGraphStore(config.kg_dir)

        # Prediction storage
        self.predictions_dir = config.data_dir / "predictions"
        self.predictions_dir.mkdir(parents=True, exist_ok=True)

        # Dispute → prediction mapping storage
        self.dispute_predictions_dir = config.data_dir / "dispute_predictions"
        self.dispute_predictions_dir.mkdir(parents=True, exist_ok=True)

        # Try to load RAG pipeline
        self._load_rag_pipeline()

        logger.info("prediction_service_initialized")

    def _load_rag_pipeline(self) -> None:
        """Try to load the RAG pipeline."""
        try:
            from rag_engine import RAGPipeline, RAGConfig

            rag_config = RAGConfig.from_env()
            rag_pipeline = RAGPipeline(config=rag_config)
            self.prediction_engine.set_rag_pipeline(rag_pipeline)

            logger.info("rag_pipeline_loaded")
        except Exception as e:
            logger.warning("rag_pipeline_not_loaded", error=str(e))

    async def check_case_ready(self, case_id: str) -> Dict[str, Any]:
        """
        Check if a case is ready for prediction.

        Only dispute issues are strictly required. Other fields improve
        prediction quality but don't block generation.
        """
        intake_service = get_intake_service()
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            return {
                "exists": False,
                "is_complete": False,
                "completeness": 0,
                "missing_info": [],
                "missing_recommended": [],
                "data_quality_tier": "insufficient",
            }

        case_file.calculate_completeness()
        missing = case_file.get_missing_required_info()
        missing_recommended = case_file.get_missing_recommended_info()
        quality_tier = case_file.get_data_quality_tier()
        is_ready = case_file.has_all_required_info()

        logger.debug(
            "case_readiness_check",
            case_id=case_id,
            completeness=case_file.completeness_score,
            is_ready=is_ready,
            data_quality_tier=quality_tier,
            missing_required=missing,
            missing_recommended=missing_recommended,
        )

        return {
            "exists": True,
            "is_complete": is_ready,
            "completeness": case_file.completeness_score,
            "missing_info": missing,
            "missing_recommended": missing_recommended,
            "data_quality_tier": quality_tier,
        }

    async def generate_prediction(
        self,
        case_id: str,
        include_reasoning: bool = True,
    ) -> PredictionResult:
        """
        Generate a prediction for a case.

        If the case belongs to a two-party dispute (both tenant and landlord
        have submitted), their CaseFiles are merged and a single shared
        prediction is generated. Both parties will receive the same result.

        Args:
            case_id: The case ID
            include_reasoning: Whether to include full reasoning trace

        Returns:
            PredictionResult with prediction and reasoning
        """
        intake_service = get_intake_service()
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            raise ValueError(f"Case not found: {case_id}")

        # Try to resolve dispute and merge both parties' data
        merged_case_file, dispute_id = await self._resolve_and_merge(
            case_id, case_file, intake_service
        )

        # Check for cached shared prediction (avoid regenerating)
        if dispute_id:
            cached = self._get_cached_dispute_prediction(dispute_id)
            if cached:
                logger.info(
                    "returning_cached_dispute_prediction",
                    case_id=case_id,
                    dispute_id=dispute_id,
                    prediction_id=cached.get("prediction_id"),
                )
                # Re-hydrate into PredictionResult
                return PredictionResult.model_validate(cached)

        # Build knowledge graph from (merged or single) case file
        kg = self.graph_builder.build(merged_case_file)
        self.kg_store.save(kg)

        logger.info(
            "generating_prediction",
            case_id=case_id,
            dispute_id=dispute_id,
            is_merged=dispute_id is not None,
            kg_nodes=len(kg.nodes),
            kg_edges=len(kg.edges),
        )

        # Generate prediction
        prediction = await self.prediction_engine.predict(
            case_file=merged_case_file,
            knowledge_graph=kg,
        )

        # Tag with dispute metadata so both parties can find it
        if dispute_id:
            prediction.metadata["dispute_id"] = dispute_id
            prediction.metadata["merged"] = True

        # Save prediction (and cache by dispute_id if applicable)
        self._save_prediction(prediction)
        if dispute_id:
            self._save_dispute_prediction_mapping(dispute_id, prediction.prediction_id)

        return prediction

    async def _resolve_and_merge(
        self,
        case_id: str,
        case_file: CaseFile,
        intake_service: Any,
    ) -> tuple:
        """
        Attempt to find a dispute for this case and merge both parties' data.

        Returns:
            (case_file, dispute_id) — merged CaseFile + dispute_id if both
            parties are present, otherwise (original case_file, None).
        """
        try:
            from apps.api.src.services.dispute_service import get_dispute_service

            dispute_service = get_dispute_service()

            # Find the session_id backing this case_id
            session_id = await intake_service.get_session_id_for_case(case_id)
            if not session_id:
                logger.debug("no_session_for_case", case_id=case_id)
                return case_file, None

            # Find the dispute linked to this session
            dispute = await dispute_service.get_dispute_by_session(session_id)
            if not dispute:
                logger.debug("no_dispute_for_session", session_id=session_id)
                return case_file, None

            logger.info(
                "dispute_found",
                dispute_id=dispute.dispute_id,
                has_both=dispute.has_both_parties,
                status=dispute.status.value,
            )

            # If only one party, use the original case file
            if not dispute.has_both_parties:
                return case_file, dispute.dispute_id

            # Load both parties' CaseFiles
            tenant_cf = None
            landlord_cf = None

            if dispute.tenant_session_id:
                tenant_cf = await intake_service.get_case_file_by_session(
                    dispute.tenant_session_id
                )
            if dispute.landlord_session_id:
                landlord_cf = await intake_service.get_case_file_by_session(
                    dispute.landlord_session_id
                )

            if tenant_cf and landlord_cf:
                merged = merge_case_files(tenant_cf, landlord_cf)
                logger.info(
                    "case_files_merged",
                    dispute_id=dispute.dispute_id,
                    tenant_issues=len(tenant_cf.issues),
                    landlord_issues=len(landlord_cf.issues),
                    merged_issues=len(merged.issues),
                    merged_evidence=len(merged.evidence),
                )
                return merged, dispute.dispute_id

            # Fallback: one party's CaseFile couldn't be loaded
            logger.warning(
                "partial_merge_fallback",
                dispute_id=dispute.dispute_id,
                has_tenant_cf=tenant_cf is not None,
                has_landlord_cf=landlord_cf is not None,
            )
            return case_file, dispute.dispute_id

        except Exception as e:
            logger.warning(
                "dispute_merge_failed",
                case_id=case_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return case_file, None

    def _get_cached_dispute_prediction(self, dispute_id: str) -> Optional[Dict]:
        """
        Check if a shared prediction already exists for this dispute.

        Returns the prediction data dict if cached, else None.
        """
        mapping_path = self.dispute_predictions_dir / f"{dispute_id}.json"
        if not mapping_path.exists():
            return None

        try:
            with open(mapping_path) as f:
                mapping = json.load(f)

            prediction_id = mapping.get("prediction_id")
            if not prediction_id:
                return None

            pred_path = self.predictions_dir / f"prediction_{prediction_id}.json"
            if not pred_path.exists():
                return None

            with open(pred_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(
                "cached_dispute_prediction_read_failed",
                dispute_id=dispute_id,
                error=str(e),
            )
            return None

    def _save_dispute_prediction_mapping(
        self, dispute_id: str, prediction_id: str
    ) -> None:
        """Save dispute_id → prediction_id mapping so both parties get the same result."""
        mapping_path = self.dispute_predictions_dir / f"{dispute_id}.json"
        data = {
            "dispute_id": dispute_id,
            "prediction_id": prediction_id,
        }

        with open(mapping_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(
            "dispute_prediction_mapping_saved",
            dispute_id=dispute_id,
            prediction_id=prediction_id,
        )

    async def get_prediction(self, prediction_id: str) -> Optional[Dict]:
        """Get a saved prediction."""
        path = self.predictions_dir / f"prediction_{prediction_id}.json"
        if not path.exists():
            return None

        with open(path) as f:
            return json.load(f)

    async def list_predictions_for_case(self, case_id: str) -> List[Dict]:
        """
        List all predictions for a case.

        Also checks if this case belongs to a dispute with a shared prediction,
        so both parties see the same result.
        """
        predictions = []
        seen_ids: set = set()

        # 1. Direct matches by case_id
        for path in self.predictions_dir.glob("prediction_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("case_id") == case_id:
                    pred_id = data.get("prediction_id")
                    if pred_id and pred_id not in seen_ids:
                        seen_ids.add(pred_id)
                        predictions.append(
                            {
                                "prediction_id": pred_id,
                                "timestamp": data.get("timestamp"),
                                "overall_outcome": data.get("overall_outcome"),
                                "overall_confidence": data.get("overall_confidence"),
                            }
                        )
            except Exception:
                continue

        # 2. Check for shared dispute prediction
        try:
            from apps.api.src.services.dispute_service import get_dispute_service

            intake_service = get_intake_service()
            dispute_service = get_dispute_service()

            session_id = await intake_service.get_session_id_for_case(case_id)
            if session_id:
                dispute = await dispute_service.get_dispute_by_session(session_id)
                if dispute:
                    cached = self._get_cached_dispute_prediction(dispute.dispute_id)
                    if cached:
                        pred_id = cached.get("prediction_id")
                        if pred_id and pred_id not in seen_ids:
                            seen_ids.add(pred_id)
                            predictions.append(
                                {
                                    "prediction_id": pred_id,
                                    "timestamp": cached.get("timestamp"),
                                    "overall_outcome": cached.get("overall_outcome"),
                                    "overall_confidence": cached.get(
                                        "overall_confidence"
                                    ),
                                }
                            )
        except Exception as e:
            logger.warning(
                "dispute_prediction_lookup_failed",
                case_id=case_id,
                error=str(e),
            )

        return predictions

    def _save_prediction(self, prediction: PredictionResult) -> None:
        """Save a prediction to disk."""
        path = self.predictions_dir / f"prediction_{prediction.prediction_id}.json"
        data = prediction.model_dump(mode="json")

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("prediction_saved", prediction_id=prediction.prediction_id)


def get_prediction_service() -> PredictionService:
    """Dependency injection for prediction service."""
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService()
    return _prediction_service
