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

    Role Identification:
        The user's role (tenant/landlord) is always set explicitly
        via the set_user_role() method, called from the frontend
        when the user clicks a role selection button. The agent
        does not infer role from natural language.

    Typical Flow:
        1. Frontend calls start_conversation() -> agent sends greeting
        2. Frontend shows "I'm a tenant" / "I'm a landlord" buttons
        3. User clicks button -> frontend calls set_user_role()
        4. Agent advances to BASIC_DETAILS and collects case info
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

        logger.debug(
            "process_message_start",
            session_id=conversation.session_id,
            current_stage=conversation.current_stage.value,
            user_message=user_message,
            history_len=len(conversation.messages),
        )

        # Add user message to history
        conversation.add_user_message(user_message)
        logger.debug(
            "user_message_added_to_history",
            session_id=conversation.session_id,
            user_message=user_message,
            messages=conversation.to_messages(),
        )

        # Handle stage transitions at GREETING
        # Role is always set explicitly via /chat/set-role endpoint from frontend
        if conversation.current_stage == IntakeStage.GREETING:
            logger.debug(
                "at_greeting_stage_checking_role",
                session_id=conversation.session_id,
                role_explicitly_set=conversation.role_explicitly_set,
            )
            if conversation.role_explicitly_set:
                conversation.advance_stage(IntakeStage.BASIC_DETAILS)
                logger.debug(
                    "advanced_to_basic_details_due_to_role_explicitly_set",
                    session_id=conversation.session_id,
                )
            # If role not set, stay at GREETING - frontend should call /chat/set-role

        # Extract facts from the message
        extraction_result = await self.extractor.extract_facts(
            user_message,
            conversation.case_file,
            conversation.current_stage,
        )
        logger.debug(
            "facts_extracted_from_message",
            session_id=conversation.session_id,
            extraction_result=str(extraction_result),
            prev_case_file=str(conversation.case_file),
        )

        conversation.case_file = extraction_result.updated_case_file

        # Track extraction success
        conversation.last_extraction_successful = not extraction_result.no_new_info
        logger.debug(
            "extraction_result_updated",
            session_id=conversation.session_id,
            last_extraction_successful=conversation.last_extraction_successful,
            updated_case_file=str(conversation.case_file),
        )

        # Determine next stage
        next_stage = self._determine_next_stage(conversation)
        logger.debug(
            "determined_next_stage",
            session_id=conversation.session_id,
            current_stage=conversation.current_stage.value,
            next_stage=next_stage.value,
        )
        if next_stage != conversation.current_stage:
            conversation.advance_stage(next_stage)
            logger.debug(
                "advanced_to_next_stage",
                session_id=conversation.session_id,
                advanced_stage=next_stage.value,
            )

        # Generate response
        response = await self._generate_response(conversation)
        logger.debug(
            "agent_response_generated",
            session_id=conversation.session_id,
            response=response,
            stage=conversation.current_stage.value,
        )
        conversation.add_assistant_message(response)

        # Check if complete
        if conversation.current_stage == IntakeStage.COMPLETE:
            conversation.mark_complete()
            self._stats["sessions_completed"] += 1
            logger.debug(
                "conversation_marked_complete",
                session_id=conversation.session_id,
                stage=conversation.current_stage.value,
            )

        logger.info(
            "intake_message_processed",
            session_id=conversation.session_id,
            stage=conversation.current_stage.value,
            completeness=conversation.case_file.completeness_score,
            message_count=len(conversation.messages),
        )

        logger.debug(
            "process_message_end",
            session_id=conversation.session_id,
            response=response,
            updated_stage=conversation.current_stage.value,
            completeness=conversation.case_file.completeness_score,
        )

        return response, conversation

    async def start_conversation(
        self,
        user_role: Optional[PartyRole] = None,
    ) -> Tuple[str, ConversationState]:
        """
        Start a new intake conversation.

        Args:
            user_role: Pre-set user role (optional). If provided, the conversation
                      will start at BASIC_DETAILS stage with role-appropriate questions.

        Returns:
            Tuple of (greeting_message, new_conversation_state)
        """
        logger.debug(
            "start_conversation_called",
            user_role=user_role.value if user_role else None,
        )
        conversation = ConversationState.new(user_role=user_role)

        # If role is provided, advance to BASIC_DETAILS immediately
        if user_role is not None:
            conversation.advance_stage(IntakeStage.BASIC_DETAILS)
            logger.debug(
                "role_provided_advancing_to_basic_details",
                session_id=conversation.session_id,
                role=user_role.value,
            )

        # Generate greeting (will be role-specific if role is set)
        greeting = await self._generate_greeting(conversation)
        logger.debug(
            "generated_greeting_for_start_conversation",
            session_id=conversation.session_id,
            greeting=greeting,
            user_role=user_role.value if user_role else None,
            stage=conversation.current_stage.value,
        )
        conversation.add_assistant_message(greeting)

        return greeting, conversation

    async def set_user_role(
        self,
        conversation: ConversationState,
        role: PartyRole,
    ) -> Tuple[str, ConversationState]:
        """
        Explicitly set the user's role (for button-triggered UI flows).

        This method supports UI flows where the user clicks a "I'm a tenant"
        or "I'm a landlord" button instead of typing their role. It sets
        the role, advances the stage appropriately, and generates a
        role-appropriate response.

        Args:
            conversation: Current conversation state
            role: The user's role (TENANT or LANDLORD)

        Returns:
            Tuple of (confirmation_message, updated_conversation_state)
        """
        logger.debug("calling_agent_set_user_role")
        # Set the role explicitly
        conversation.set_role(role)

        logger.debug(
            "conversation_role_set",
            session_id=conversation.session_id,
            role=role.value,
            stage=conversation.current_stage.value,
        )
        # If we're at GREETING or ROLE_IDENTIFICATION, advance to BASIC_DETAILS
        if conversation.current_stage in (IntakeStage.GREETING, IntakeStage.ROLE_IDENTIFICATION):
            conversation.advance_stage(IntakeStage.BASIC_DETAILS)
        logger.debug(
            "advanced_to_basic_details_due_to_role_explicitly_set",
            session_id=conversation.session_id,
        )
        # Generate a role-appropriate response to continue the conversation
        response = await self._generate_response(conversation)
        logger.debug(
            "generated_response_for_role_explicitly_set",
            session_id=conversation.session_id,
            response=response,
        )
        conversation.add_assistant_message(response)
        logger.debug(
            "assistant_message_added_to_history",
            session_id=conversation.session_id,
            response=response,
            messages=conversation.to_messages(),
        )
        logger.debug(
            "user_role_set_explicitly",
            session_id=conversation.session_id,
            role=role.value,
            stage=conversation.current_stage.value,
        )

        return response, conversation

    
    def _determine_next_stage(self, conversation: ConversationState) -> IntakeStage:
        """Determine the appropriate next stage based on collected info."""
        cf = conversation.case_file
        current = conversation.current_stage

        # Role is always set explicitly via /chat/set-role endpoint from frontend
        # Once set, advance to BASIC_DETAILS
        if current == IntakeStage.ROLE_IDENTIFICATION:
            if conversation.role_explicitly_set:
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
        logger.debug(
            "generating_response",
            session_id=conversation.session_id,
            current_stage=conversation.current_stage.value,
        )
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
        logger.debug(
            "built_response_context",
            session_id=conversation.session_id,
            context=context,
        )
        # Generate response
        response = await self.llm.generate(
            messages=conversation.to_messages(),
            system_prompt=f"{system_prompt}\n\nCURRENT STAGE GUIDANCE:\n{context}",
            max_tokens=1024,
            temperature=0.7,
        )

        return response

    async def _generate_greeting(self, conversation: ConversationState) -> str:
        """
        Generate the initial greeting message.
        
        If role is set and we're at BASIC_DETAILS, generate a role-appropriate
        first question. Otherwise, generate a generic greeting.
        """
        if conversation.case_file.user_role == PartyRole.LANDLORD:
            system_prompt = LANDLORD_SYSTEM_PROMPT
            # If we're at BASIC_DETAILS (role is set), use basic_details prompt
            if conversation.current_stage == IntakeStage.BASIC_DETAILS:
                stage_prompt = LANDLORD_STAGE_PROMPTS.get("basic_details", LANDLORD_STAGE_PROMPTS["greeting"])
            else:
                stage_prompt = LANDLORD_STAGE_PROMPTS["greeting"]
        elif conversation.case_file.user_role == PartyRole.TENANT:
            system_prompt = TENANT_SYSTEM_PROMPT
            # If we're at BASIC_DETAILS (role is set), use basic_details prompt
            if conversation.current_stage == IntakeStage.BASIC_DETAILS:
                stage_prompt = TENANT_STAGE_PROMPTS.get("basic_details", TENANT_STAGE_PROMPTS["greeting"])
            else:
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
