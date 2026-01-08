"""
Prediction service.

Orchestrates prediction generation with RAG integration.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from llm_orchestrator.config import LLMConfig
from llm_orchestrator.clients.claude_client import ClaudeClient
from llm_orchestrator.agents.prediction_agent import PredictionEngine
from llm_orchestrator.models.prediction import PredictionResult

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
    """

    def __init__(self):
        """Initialize the prediction service."""
        # Initialize components
        llm_config = LLMConfig.from_env()
        self.llm_client = ClaudeClient(api_key=llm_config.anthropic_api_key)

        # Prediction engine (RAG pipeline loaded lazily)
        self.prediction_engine = PredictionEngine(
            llm_client=self.llm_client,
            rag_pipeline=None,  # Will be set when needed
        )

        # Knowledge graph
        self.graph_builder = GraphBuilder()
        self.kg_store = JSONGraphStore(config.kg_dir)

        # Prediction storage
        self.predictions_dir = config.data_dir / "predictions"
        self.predictions_dir.mkdir(parents=True, exist_ok=True)

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

        NOW ENFORCES: ALL required fields must be present (100% of required info).
        Predictions are blocked until every required field has a value.

        Returns:
            Dict with exists, is_complete, completeness, missing_info
        """
        intake_service = get_intake_service()
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            return {
                "exists": False,
                "is_complete": False,
                "completeness": 0,
                "missing_info": [],
            }

        case_file.calculate_completeness()
        missing = case_file.get_missing_required_info()

        # STRICT VALIDATION: Require ALL required fields (not just 70%)
        is_ready = case_file.has_all_required_info()

        logger.debug(
            "case_readiness_check",
            case_id=case_id,
            completeness=case_file.completeness_score,
            has_all_required=is_ready,
            missing_count=len(missing),
            missing_fields=missing,
        )

        return {
            "exists": True,
            "is_complete": is_ready,  # Only true if ALL required fields present
            "completeness": case_file.completeness_score,
            "missing_info": missing,
        }

    async def generate_prediction(
        self,
        case_id: str,
        include_reasoning: bool = True,
    ) -> PredictionResult:
        """
        Generate a prediction for a case.

        Args:
            case_id: The case ID
            include_reasoning: Whether to include full reasoning trace

        Returns:
            PredictionResult with prediction and reasoning
        """
        # Get case file
        intake_service = get_intake_service()
        case_file = await intake_service.get_case_file(case_id)

        if not case_file:
            raise ValueError(f"Case not found: {case_id}")

        # Build knowledge graph
        kg = self.graph_builder.build(case_file)
        self.kg_store.save(kg)

        logger.info(
            "generating_prediction",
            case_id=case_id,
            kg_nodes=len(kg.nodes),
            kg_edges=len(kg.edges),
        )

        # Generate prediction
        prediction = await self.prediction_engine.predict(
            case_file=case_file,
            knowledge_graph=kg,
        )

        # Save prediction
        self._save_prediction(prediction)

        return prediction

    async def get_prediction(self, prediction_id: str) -> Optional[Dict]:
        """Get a saved prediction."""
        path = self.predictions_dir / f"prediction_{prediction_id}.json"
        if not path.exists():
            return None

        with open(path) as f:
            return json.load(f)

    async def list_predictions_for_case(self, case_id: str) -> List[Dict]:
        """List all predictions for a case."""
        predictions = []

        for path in self.predictions_dir.glob("prediction_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("case_id") == case_id:
                    predictions.append({
                        "prediction_id": data.get("prediction_id"),
                        "timestamp": data.get("timestamp"),
                        "overall_outcome": data.get("overall_outcome"),
                        "overall_confidence": data.get("overall_confidence"),
                    })
            except Exception:
                continue

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
