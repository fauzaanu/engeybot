"""Agentic handler orchestrating the full research pipeline."""

import uuid
from datetime import datetime
from typing import Optional

from google import genai
from huey import RedisHuey



from agentic.decomposer import QueryDecomposer, ClarificationResult
from agentic.models import ConversationState, ProcessingStage, SynthesizedResponse, ResearchResult
from agentic.mongo_store import MongoStore
from agentic.researcher import ResearchEngine
from agentic.status_manager import StatusManager, format_sources_html
from agentic.synthesizer import SynthesisEngine

# In-memory store for pending clarifications (chat_id -> conversation_id)
_pending_clarifications: dict[int, str] = {}


class AgenticHandler:
    """Orchestrates the full agentic research pipeline.
    
    This handler coordinates:
    1. Sending initial status message
    2. Check if clarification is needed
    3. Build detailed research prompt
    4. Single grounded search
    5. Summarize response
    6. Persisting state to MongoDB at each stage
    """
    
    def __init__(
        self,
        bot,
        gemini_client: genai.Client,
        mongo_store: MongoStore,
        huey: Optional[RedisHuey] = None,
    ):
        """Initialize AgenticHandler with required dependencies.
        
        Args:
            bot: TeleBot instance for sending messages
            gemini_client: Google GenAI client for Gemini API calls
            mongo_store: MongoStore instance for persistence
            huey: Optional RedisHuey instance for scheduling auto-delete
        """
        self.bot = bot
        self.status_manager = StatusManager(bot, huey)
        self.decomposer = QueryDecomposer(gemini_client)
        self.researcher = ResearchEngine(gemini_client)
        self.synthesizer = SynthesisEngine(gemini_client)
        self.store = mongo_store

    def handle(self, message) -> None:
        """Process a message through the simplified agentic pipeline.
        
        Flow:
        1. Check if this is a clarification response
        2. Send initial "Thinking..." status
        3. Check if clarification is needed
        4. Single grounded search with detailed prompt
        5. Summarize response
        
        Args:
            message: Telegram message object with chat.id, message_id, 
                     from_user.id, and text attributes
        """
        chat_id = message.chat.id
        user_id = message.from_user.id
        message_id = message.message_id
        question = message.text
        
        # Check if this is a response to a pending clarification
        if chat_id in _pending_clarifications:
            conversation_id = _pending_clarifications[chat_id]
            self._handle_clarification_response(chat_id, conversation_id, question, message_id)
            return
        
        # Create conversation state
        conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
        state = ConversationState(
            id=conversation_id,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            original_question=question,
            stage=ProcessingStage.THINKING,
        )
        
        # Step 1: Send initial status message
        try:
            status_message_id = self.status_manager.send_initial_status(chat_id, message_id)
            state.status_message_id = status_message_id
        except Exception as e:
            status_message_id = None
            state.error_message = f"Failed to send status: {e}"
        
        # Persist initial state
        try:
            self.store.create_conversation(state)
        except Exception:
            pass
        
        # Step 2: Check if clarification is needed
        try:
            context = "\n".join(state.clarification_context) if state.clarification_context else ""
            clarification_result = self.decomposer.check_clarification_needed(question, context)
            
            if clarification_result.needs_clarification and clarification_result.clarification_question:
                self._ask_clarification(state, status_message_id, clarification_result)
                return
        except Exception as e:
            print(f"Clarification check failed: {e}")
        
        # Continue with research
        self._do_research(state, status_message_id)
    
    def _do_research(self, state: ConversationState, status_message_id: Optional[int]) -> None:
        """Execute the research and synthesis pipeline.
        
        Args:
            state: Conversation state
            status_message_id: Status message ID for updates
        """
        chat_id = state.chat_id
        conversation_id = state.id
        
        # Build full question with clarification context
        full_question = state.original_question
        if state.clarification_context:
            full_question = f"{state.original_question}\n\nContext:\n" + "\n".join(state.clarification_context)
        
        # Step 3: Single grounded search
        try:
            self._update_stage(state, ProcessingStage.RESEARCHING, status_message_id)
            
            research_result = self.researcher.research_single(full_question)
            state.research_results = [research_result]
            
            self._persist_update(conversation_id, {
                "research_results": [research_result.model_dump(mode="json")],
                "stage": ProcessingStage.RESEARCHING.value,
            })
            
            if not research_result.success:
                self._handle_failure(state, status_message_id, "Research failed")
                return
                
        except Exception as e:
            self._handle_failure(state, status_message_id, f"Research failed: {e}")
            return
        
        # Step 4: Summarize response
        try:
            self._update_stage(state, ProcessingStage.SYNTHESIZING, status_message_id)
            
            final_response = self.synthesizer.summarize(
                full_question,
                research_result,
            )
            state.final_response = final_response
            state.stage = ProcessingStage.COMPLETE
            state.completed_at = datetime.utcnow()
            
            self._persist_update(conversation_id, {
                "final_response": final_response.model_dump(mode="json"),
                "stage": ProcessingStage.COMPLETE.value,
                "completed_at": state.completed_at.isoformat(),
            })
            print(f"Synthesis complete: {len(final_response.response_text)} chars")
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Fallback: use research result directly
            final_response = SynthesizedResponse(
                response_text=research_result.response_text[:500] if research_result.response_text else "ނަތީޖާއެއް ނުލިބުނު",
                sources=research_result.sources,
                sections=[],
                follow_up_questions=[],
            )
            state.final_response = final_response
            state.error_message = f"Synthesis failed: {e}"
            self._persist_update(conversation_id, {
                "final_response": final_response.model_dump(mode="json"),
                "stage": ProcessingStage.COMPLETE.value,
                "error_message": state.error_message,
            })
        
        self._send_final_response(chat_id, status_message_id, final_response)
    
    def _ask_clarification(
        self,
        state: ConversationState,
        status_message_id: Optional[int],
        clarification_result: ClarificationResult,
    ) -> None:
        """Ask the user for clarification with numbered options.
        
        Args:
            state: Current conversation state
            status_message_id: Status message ID to replace
            clarification_result: The clarification result with question and options
        """
        clarification_question = clarification_result.clarification_question
        state.stage = ProcessingStage.AWAITING_CLARIFICATION
        state.pending_clarification = clarification_question
        
        # Store pending clarification
        _pending_clarifications[state.chat_id] = state.id
        
        # Store options for later lookup
        if clarification_result.options:
            state.pending_options = [opt.value for opt in clarification_result.options]
        
        self._persist_update(state.id, {
            "stage": ProcessingStage.AWAITING_CLARIFICATION.value,
            "pending_clarification": clarification_question,
            "pending_options": state.pending_options if hasattr(state, 'pending_options') else [],
        })
        
        # Build message with numbered options
        message_text = clarification_question
        if clarification_result.options:
            message_text += "\n\n"
            for i, option in enumerate(clarification_result.options, 1):
                message_text += f"{i}. {option.label}\n"
        
        # Delete status message and send clarification
        if status_message_id:
            try:
                self.bot.delete_message(state.chat_id, status_message_id)
            except Exception:
                pass
        
        # Send clarification question with numbered options
        self.bot.send_message(
            state.chat_id,
            message_text,
            reply_to_message_id=state.message_id,
            disable_web_page_preview=True,
        )
    

    
    def _handle_clarification_response(
        self,
        chat_id: int,
        conversation_id: str,
        response: str,
        message_id: int,
    ) -> None:
        """Handle a user's response to a clarification question.
        
        Args:
            chat_id: Telegram chat ID
            conversation_id: The conversation awaiting clarification
            response: The user's response (can be a number or free text)
            message_id: The message ID of the response
        """
        # Remove from pending
        del _pending_clarifications[chat_id]
        
        # Get conversation state
        state = self.store.get_conversation(conversation_id)
        if not state:
            return
        
        # Check if response is a number selecting an option
        actual_response = response
        if state.pending_options and response.strip().isdigit():
            option_num = int(response.strip())
            if 1 <= option_num <= len(state.pending_options):
                actual_response = state.pending_options[option_num - 1]
        
        # Add clarification to context
        clarification_qa = f"Q: {state.pending_clarification}\nA: {actual_response}"
        state.clarification_context.append(clarification_qa)
        state.pending_clarification = None
        state.pending_options = []
        
        self._persist_update(conversation_id, {
            "clarification_context": state.clarification_context,
            "pending_clarification": None,
            "pending_options": [],
        })
        
        # Send new status message
        try:
            status_message_id = self.status_manager.send_initial_status(chat_id, message_id)
            state.status_message_id = status_message_id
            self._persist_update(conversation_id, {"status_message_id": status_message_id})
        except Exception:
            status_message_id = None
        
        # Check if more clarification is needed
        try:
            context = "\n".join(state.clarification_context)
            clarification_result = self.decomposer.check_clarification_needed(
                state.original_question, context
            )
            
            if clarification_result.needs_clarification and clarification_result.clarification_question:
                self._ask_clarification(state, status_message_id, clarification_result)
                return
        except Exception as e:
            print(f"Clarification check failed: {e}")
        
        # Proceed with research
        self._continue_research(state, status_message_id)
    
    def _continue_research(
        self,
        state: ConversationState,
        status_message_id: Optional[int],
    ) -> None:
        """Continue the research pipeline after clarifications are complete.
        
        Args:
            state: Conversation state with clarifications
            status_message_id: Status message ID for updates
        """
        # Simply delegate to the main research method
        self._do_research(state, status_message_id)
    
    def _update_stage(
        self,
        state: ConversationState,
        stage: ProcessingStage,
        status_message_id: Optional[int],
    ) -> None:
        """Update processing stage and status message.
        
        Args:
            state: Current conversation state
            stage: New processing stage
            status_message_id: Status message ID to update (if any)
        """
        state.stage = stage
        if status_message_id:
            try:
                self.status_manager.update_status(
                    state.chat_id,
                    status_message_id,
                    stage,
                )
            except Exception:
                pass  # Continue even if status update fails
    
    def _persist_update(self, conversation_id: str, updates: dict) -> None:
        """Persist updates to MongoDB, ignoring failures.
        
        Args:
            conversation_id: Conversation ID to update
            updates: Dictionary of fields to update
        """
        try:
            self.store.update_conversation(conversation_id, updates)
        except Exception:
            pass  # Continue processing even if persistence fails
    
    def _handle_failure(
        self,
        state: ConversationState,
        status_message_id: Optional[int],
        error_message: str,
    ) -> None:
        """Handle pipeline failure by updating state and notifying user.
        
        Args:
            state: Current conversation state
            status_message_id: Status message ID to update
            error_message: Error message to display
        """
        state.stage = ProcessingStage.FAILED
        state.error_message = error_message
        
        self._persist_update(state.id, {
            "stage": ProcessingStage.FAILED.value,
            "error_message": error_message,
        })
        
        if status_message_id:
            try:
                self.status_manager.replace_with_response(
                    state.chat_id,
                    status_message_id,
                    f"❌ Sorry, I encountered an error: {error_message}",
                )
            except Exception:
                # Try sending a new message if edit fails
                try:
                    self.status_manager.send_with_auto_delete(
                        state.chat_id,
                        f"❌ Sorry, I encountered an error: {error_message}",
                        reply_to=state.message_id,
                    )
                except Exception:
                    pass
    
    def _create_fallback_response(
        self,
        research_results: list,
    ) -> SynthesizedResponse:
        """Create a fallback response by concatenating research results.
        
        Used when synthesis fails.
        
        Args:
            research_results: List of ResearchResult objects
            
        Returns:
            SynthesizedResponse with concatenated results
        """
        from agentic.models import SourceInfo
        
        parts = []
        all_sources: list[SourceInfo] = []
        seen_urls: set[str] = set()
        
        for i, result in enumerate(research_results, start=1):
            if result.success and result.response_text:
                parts.append(f"**Finding {i}:**\n{result.response_text}")
                
                for source in result.sources:
                    if source.url and source.url not in seen_urls:
                        seen_urls.add(source.url)
                        all_sources.append(source)
        
        response_text = "\n\n".join(parts) if parts else "No results found."
        
        return SynthesizedResponse(
            response_text=response_text,
            sources=all_sources,
            sections=[],
        )
    
    def _split_message(self, text: str, max_length: int = 4096) -> list[str]:
        """Split a long message into chunks that fit Telegram's limit.
        
        Args:
            text: The text to split
            max_length: Maximum length per chunk (default 4096)
            
        Returns:
            List of text chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        for line in text.split("\n"):
            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                if len(line) > max_length:
                    # Split long lines
                    for i in range(0, len(line), max_length):
                        chunks.append(line[i:i + max_length])
                    current_chunk = ""
                else:
                    current_chunk = line + "\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _send_final_response(
        self,
        chat_id: int,
        status_message_id: Optional[int],
        response: SynthesizedResponse,
    ) -> None:
        """Send the final synthesized response to the user.
        
        Args:
            chat_id: Telegram chat ID
            status_message_id: Status message ID to replace
            response: The synthesized response to send
        """
        # Main response text (no HTML)
        text = response.response_text
        
        # Sources will be sent separately with HTML
        sources_text = ""
        if response.sources:
            sources_html = format_sources_html(response.sources)
            sources_text = f"މައުލޫމާތު: {sources_html}"
        
        print(f"Sending final response ({len(text)} chars) to chat {chat_id}")
        
        # Send main response (plain text, no HTML parsing issues)
        if status_message_id:
            try:
                self.status_manager.replace_with_response(
                    chat_id,
                    status_message_id,
                    text,
                    parse_mode=None,  # Plain text
                )
                print("Successfully replaced status with response")
            except Exception as e:
                print(f"Failed to replace status: {e}")
                # If edit fails, send a new message
                try:
                    self.status_manager.send_with_auto_delete(
                        chat_id,
                        text,
                        parse_mode=None,
                    )
                    print("Sent new message instead")
                except Exception as e2:
                    print(f"Failed to send new message: {e2}")
        else:
            # No status message, send new message
            try:
                self.status_manager.send_with_auto_delete(
                    chat_id,
                    text,
                    parse_mode=None,
                )
                print("Sent new message (no status message)")
            except Exception as e:
                print(f"Failed to send message: {e}")
        
        # Send sources separately with HTML (if any)
        if sources_text:
            try:
                self.status_manager.send_with_auto_delete(
                    chat_id,
                    sources_text,
                    parse_mode="HTML",
                )
                print("Sent sources")
            except Exception as e:
                print(f"Failed to send sources: {e}")
        

