"""Pydantic models for agentic chat data structures."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProcessingStage(str, Enum):
    """Processing stages for agentic conversation flow."""
    THINKING = "thinking"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    DECOMPOSING = "decomposing"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    FAILED = "failed"


class SourceInfo(BaseModel):
    """Source information with display title and full URL."""
    title: str = Field(description="Short display title for the source")
    url: str = Field(description="Full URL to the source")

    def to_html(self) -> str:
        """Render source as HTML hyperlink for Telegram display."""
        return f'<a href="{self.url}">{self.title}</a>'


class SubQuery(BaseModel):
    """A derived question for researching a specific aspect."""
    id: str = Field(description="Unique identifier for the sub-query")
    query_text: str = Field(description="The sub-query text to research")
    aspect: str = Field(description="The aspect of the original question this covers")


class ResearchResult(BaseModel):
    """Result from a grounded search for a sub-query."""
    sub_query_id: str = Field(description="Reference to the sub-query")
    response_text: str = Field(description="The research response text")
    sources: list[SourceInfo] = Field(default_factory=list, description="Source info with title and URL")
    success: bool = Field(default=True, description="Whether the search succeeded")
    error_message: Optional[str] = Field(default=None, description="Error if search failed")


class FollowUpQuestion(BaseModel):
    """A suggested follow-up question."""
    question: str = Field(description="The follow-up question text")
    topic: str = Field(description="Brief topic for button label")


class SynthesizedResponse(BaseModel):
    """The final combined response from all research."""
    response_text: str = Field(description="The synthesized response text")
    sources: list[SourceInfo] = Field(default_factory=list, description="Combined unique sources with title and URL")
    sections: list[str] = Field(default_factory=list, description="Section headings used")
    follow_up_questions: list[FollowUpQuestion] = Field(
        default_factory=list, 
        description="Suggested follow-up questions"
    )


class ConversationState(BaseModel):
    """Complete state of an agentic conversation."""
    id: str = Field(description="Unique conversation identifier")
    user_id: int = Field(description="Telegram user ID")
    chat_id: int = Field(description="Telegram chat ID")
    message_id: int = Field(description="Original message ID")
    status_message_id: Optional[int] = Field(default=None, description="Status message ID for updates")
    original_question: str = Field(description="The user's original question")
    clarification_context: list[str] = Field(
        default_factory=list,
        description="List of clarification Q&A pairs"
    )
    pending_clarification: Optional[str] = Field(
        default=None,
        description="The clarifying question waiting for user response"
    )
    pending_options: list[str] = Field(
        default_factory=list,
        description="List of option values for numbered selection"
    )
    stage: ProcessingStage = Field(default=ProcessingStage.THINKING)
    sub_queries: list[SubQuery] = Field(default_factory=list)
    research_results: list[ResearchResult] = Field(default_factory=list)
    final_response: Optional[SynthesizedResponse] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
