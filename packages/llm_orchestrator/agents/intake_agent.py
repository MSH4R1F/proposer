"""
Conversational intake agent.

Guides users through a structured interview to collect
case facts for tenancy deposit disputes.
"""

from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..clients.base import BaseLLMClient
from ..models.case_file import CaseFile, PartyRole
from ..models.conversation import ConversationState, IntakeStage
from ..extractors.fact_extractor import FactExtractor
from ..prompts.tenant_intake import (
    TENANT_SYSTEM_PROMPT,
    TENANT_STAGE_PROMPTS,
)
from ..prompts.landlord_intake import (
    LANDLORD_SYSTEM_PROMPT,
    LANDLORD_STAGE_PROMPTS,
)
from .base import BaseAgent

logger = structlog.get_logger()


class IntakeAgent(BaseAgent):
    """
    Conversational agent for case intake.

    Guides users (tenant or landlord) through a structured
    interview to collect case facts, adapting questions
    based on their role and previous answers.
    """

    # Stage transition requirements
    STAGE_REQUIREMENTS = {
        IntakeStage.GREETING: [],
        IntakeStage.ROLE_IDENTIFICATION: [],
        IntakeStage.BASIC_DETAILS: ["property.address"],
        IntakeStage.TENANCY_DETAILS: ["tenancy.start_date"],
        IntakeStage.DEPOSIT_DETAILS: ["tenancy.deposit_amount", "tenancy.deposit_protected"],
        IntakeStage.ISSUE_IDENTIFICATION: ["issues"],
        IntakeStage.EVIDENCE_COLLECTION: [],  # Can proceed without
        IntakeStage.CLAIM_AMOUNTS: [],  # Can proceed without
        IntakeStage.NARRATIVE: [],  # Can proceed without
        IntakeStage.CONFIRMATION: [],
        IntakeStage.COMPLETE: [],
    }

    # Maximum attempts per stage before moving on
    MAX_STAGE_ATTEMPTS = 3

    def __init__(
        self,
        llm_client: BaseLLMClient,
        fact_extractor: Optional[FactExtractor] = None,
    ):
        """
        Initialize the intake agent.

        Args:
            llm_client: LLM client for conversation
            fact_extractor: Extractor for parsing facts (optional, will create if not provided)
        """
        self.llm = llm_client
        self.extractor = fact_extractor or FactExtractor(llm_client)
        self._stats = {"messages_processed": 0, "sessions_completed": 0}

    async def process_message(
        self,
        conversation: ConversationState,
        user_message: str,
    ) -> Tuple[str, ConversationState]:
        """
        Process a user message and return agent response.

        Args:
            conversation: Current conversation state
            user_message: The user's message

        Returns:
            Tuple of (agent_response, updated_conversation_state)
        """
        self._stats["messages_processed"] += 1

        # Add user message to history
        conversation.add_user_message(user_message)

        # Handle first message - check for role identification
        if conversation.current_stage == IntakeStage.GREETING:
            role = self._detect_role(user_message)
            if role:
                conversation.case_file.user_role = role
                conversation.advance_stage(IntakeStage.BASIC_DETAILS)
            else:
                conversation.advance_stage(IntakeStage.ROLE_IDENTIFICATION)

        # Extract facts from the message
        extraction_result = await self.extractor.extract_facts(
            user_message,
            conversation.case_file,
            conversation.current_stage,
        )
        conversation.case_file = extraction_result.updated_case_file

        # Track extraction success
        conversation.last_extraction_successful = not extraction_result.no_new_info

        # Determine next stage
        next_stage = self._determine_next_stage(conversation)
        if next_stage != conversation.current_stage:
            conversation.advance_stage(next_stage)

        # Generate response
        response = await self._generate_response(conversation)
        conversation.add_assistant_message(response)

        # Check if complete
        if conversation.current_stage == IntakeStage.COMPLETE:
            conversation.mark_complete()
            self._stats["sessions_completed"] += 1

        logger.info(
            "intake_message_processed",
            session_id=conversation.session_id,
            stage=conversation.current_stage.value,
            completeness=conversation.case_file.completeness_score,
            message_count=len(conversation.messages),
        )

        return response, conversation

    async def start_conversation(
        self,
        user_role: Optional[PartyRole] = None,
    ) -> Tuple[str, ConversationState]:
        """
        Start a new intake conversation.

        Args:
            user_role: Pre-set user role (optional)

        Returns:
            Tuple of (greeting_message, new_conversation_state)
        """
        conversation = ConversationState.new(user_role=user_role)

        # Generate greeting
        greeting = await self._generate_greeting(conversation)
        conversation.add_assistant_message(greeting)

        return greeting, conversation

    def _detect_role(self, message: str) -> Optional[PartyRole]:
        """Detect if the user has identified their role."""
        message_lower = message.lower()

        tenant_indicators = [
            "i am a tenant",
            "i'm a tenant",
            "i am the tenant",
            "i'm the tenant",
            "as a tenant",
            "tenant here",
            "i rented",
            "my landlord",
            "i was renting",
        ]

        landlord_indicators = [
            "i am a landlord",
            "i'm a landlord",
            "i am the landlord",
            "i'm the landlord",
            "as a landlord",
            "landlord here",
            "i let",
            "my tenant",
            "i was letting",
            "i own",
            "property owner",
        ]

        for indicator in tenant_indicators:
            if indicator in message_lower:
                return PartyRole.TENANT

        for indicator in landlord_indicators:
            if indicator in message_lower:
                return PartyRole.LANDLORD

        return None

    def _determine_next_stage(self, conversation: ConversationState) -> IntakeStage:
        """Determine the appropriate next stage based on collected info."""
        cf = conversation.case_file
        current = conversation.current_stage

        # If role not yet determined, stay there
        if current == IntakeStage.ROLE_IDENTIFICATION:
            if cf.user_role:
                return IntakeStage.BASIC_DETAILS
            return current

        # Stage progression based on what we have
        if current == IntakeStage.BASIC_DETAILS:
            if cf.property.address:
                return IntakeStage.TENANCY_DETAILS
            conversation.current_stage_attempts += 1
            if conversation.current_stage_attempts >= self.MAX_STAGE_ATTEMPTS:
                return IntakeStage.TENANCY_DETAILS
            return current

        if current == IntakeStage.TENANCY_DETAILS:
            if cf.tenancy.start_date:
                return IntakeStage.DEPOSIT_DETAILS
            conversation.current_stage_attempts += 1
            if conversation.current_stage_attempts >= self.MAX_STAGE_ATTEMPTS:
                return IntakeStage.DEPOSIT_DETAILS
            return current

        if current == IntakeStage.DEPOSIT_DETAILS:
            if cf.tenancy.deposit_amount is not None and cf.tenancy.deposit_protected is not None:
                return IntakeStage.ISSUE_IDENTIFICATION
            conversation.current_stage_attempts += 1
            if conversation.current_stage_attempts >= self.MAX_STAGE_ATTEMPTS:
                return IntakeStage.ISSUE_IDENTIFICATION
            return current

        if current == IntakeStage.ISSUE_IDENTIFICATION:
            if cf.issues:
                return IntakeStage.EVIDENCE_COLLECTION
            conversation.current_stage_attempts += 1
            if conversation.current_stage_attempts >= self.MAX_STAGE_ATTEMPTS:
                return IntakeStage.EVIDENCE_COLLECTION
            return current

        if current == IntakeStage.EVIDENCE_COLLECTION:
            # Evidence is optional, move on after one exchange
            return IntakeStage.CLAIM_AMOUNTS

        if current == IntakeStage.CLAIM_AMOUNTS:
            # Claims are optional, move on after one exchange
            return IntakeStage.NARRATIVE

        if current == IntakeStage.NARRATIVE:
            # Narrative is optional, move on after one exchange
            return IntakeStage.CONFIRMATION

        if current == IntakeStage.CONFIRMATION:
            # Check for confirmation keywords
            last_msg = conversation.get_last_user_message()
            if last_msg:
                msg_lower = last_msg.content.lower()
                if any(word in msg_lower for word in ["yes", "correct", "right", "confirm", "looks good", "that's right"]):
                    return IntakeStage.COMPLETE
            return current

        return current

    async def _generate_response(self, conversation: ConversationState) -> str:
        """Generate a response based on current conversation state."""
        # Get role-specific prompts
        if conversation.case_file.user_role == PartyRole.LANDLORD:
            system_prompt = LANDLORD_SYSTEM_PROMPT
            stage_prompts = LANDLORD_STAGE_PROMPTS
        else:
            system_prompt = TENANT_SYSTEM_PROMPT
            stage_prompts = TENANT_STAGE_PROMPTS

        # Get stage-specific guidance
        stage_guidance = stage_prompts.get(
            conversation.current_stage.value,
            "Continue the conversation naturally, collecting relevant information."
        )

        # Build context for the response
        context = self._build_response_context(conversation, stage_guidance)

        # Generate response
        response = await self.llm.generate(
            messages=conversation.to_messages(),
            system_prompt=f"{system_prompt}\n\nCURRENT STAGE GUIDANCE:\n{context}",
            max_tokens=1024,
            temperature=0.7,
        )

        return response

    async def _generate_greeting(self, conversation: ConversationState) -> str:
        """Generate the initial greeting message."""
        if conversation.case_file.user_role == PartyRole.LANDLORD:
            system_prompt = LANDLORD_SYSTEM_PROMPT
            stage_prompt = LANDLORD_STAGE_PROMPTS["greeting"]
        elif conversation.case_file.user_role == PartyRole.TENANT:
            system_prompt = TENANT_SYSTEM_PROMPT
            stage_prompt = TENANT_STAGE_PROMPTS["greeting"]
        else:
            # Generic greeting when role unknown
            system_prompt = TENANT_SYSTEM_PROMPT  # Default
            stage_prompt = """Start with a warm greeting. Explain that you help with tenancy deposit disputes.
Ask them to first tell you whether they are a tenant or a landlord, and then briefly describe their situation."""

        response = await self.llm.generate(
            messages=[{"role": "user", "content": "Start the conversation"}],
            system_prompt=f"{system_prompt}\n\nINSTRUCTION: {stage_prompt}",
            max_tokens=512,
            temperature=0.8,
        )

        return response

    def _build_response_context(
        self, conversation: ConversationState, stage_guidance: str
    ) -> str:
        """Build context for response generation."""
        cf = conversation.case_file

        context_parts = [stage_guidance, ""]

        # Add current case state
        context_parts.append("INFORMATION COLLECTED SO FAR:")

        if cf.property.address:
            context_parts.append(f"- Property: {cf.property.address}")

        if cf.tenancy.start_date:
            context_parts.append(f"- Tenancy start: {cf.tenancy.start_date}")

        if cf.tenancy.end_date:
            context_parts.append(f"- Tenancy end: {cf.tenancy.end_date}")

        if cf.tenancy.deposit_amount:
            context_parts.append(f"- Deposit: £{cf.tenancy.deposit_amount}")

        if cf.tenancy.deposit_protected is not None:
            status = "Protected" if cf.tenancy.deposit_protected else "NOT PROTECTED"
            context_parts.append(f"- Deposit protection: {status}")

        if cf.issues:
            issues_str = ", ".join(i.value for i in cf.issues)
            context_parts.append(f"- Issues: {issues_str}")

        if cf.evidence:
            ev_str = ", ".join(e.type.value for e in cf.evidence)
            context_parts.append(f"- Evidence mentioned: {ev_str}")

        # Add missing info
        missing = cf.get_missing_required_info()
        if missing:
            context_parts.append(f"\nSTILL NEEDED: {', '.join(missing)}")

        # Add completeness
        context_parts.append(f"\nCompleteness: {cf.completeness_score:.0%}")

        return "\n".join(context_parts)

    def calculate_completeness(self, case_file: CaseFile) -> float:
        """Calculate how complete the case file is."""
        return case_file.calculate_completeness()

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            **self._stats,
            "llm_stats": self.llm.get_stats() if hasattr(self.llm, "get_stats") else {},
        }
