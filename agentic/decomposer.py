"""Query decomposition using Gemini to break down complex questions."""

import uuid
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from agentic.models import SubQuery


class ClarificationOption(BaseModel):
    """A single option for clarification."""
    label: str = Field(description="Short button label in Dhivehi (max 30 chars)")
    value: str = Field(description="The interpretation this option represents")


class ClarificationResult(BaseModel):
    """Result of analyzing if clarification is needed."""
    needs_clarification: bool = Field(
        description="True if the question is ambiguous and needs clarification"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="The clarifying question to ask the user (in Dhivehi)"
    )
    options: list[ClarificationOption] = Field(
        default_factory=list,
        description="2-4 options for the user to choose from (for inline buttons)"
    )
    reason: str = Field(description="Why clarification is or isn't needed")


class SubQueryItem(BaseModel):
    """A single sub-query item for structured output."""
    query_text: str = Field(description="The sub-query text to research")
    aspect: str = Field(description="The aspect of the original question this covers")


class SubQueryList(BaseModel):
    """Structured output for query decomposition."""
    sub_queries: list[SubQueryItem] = Field(
        description="List of 2-5 sub-queries covering different aspects",
        min_length=2,
        max_length=5
    )
    reasoning: str = Field(description="Brief explanation of how the question was decomposed")


CLARIFICATION_PROMPT = """You are a smart assistant analyzing if a question needs clarification BEFORE doing any research.

User's question: {question}

Previous clarifications (if any): {context}

IMPORTANT: You must identify ambiguity BEFORE research begins. Think carefully:

ASK FOR CLARIFICATION if:
1. A word/term could refer to MULTIPLE DIFFERENT things (e.g., "Rasmalai" could be a city project OR a dessert)
2. The question is about a person/place/thing that has namesakes or homonyms
3. The user mentions something that exists in multiple contexts (politics, food, entertainment, etc.)
4. Time period is unclear and would significantly change the answer
5. Geographic context is missing and matters
6. The user uses pronouns or references without clear antecedents

DO NOT ask for clarification if:
1. The question is clear even if broad
2. There's only ONE reasonable interpretation
3. Context already provided answers the ambiguity

Think step by step:
1. What could this question be about?
2. Are there multiple VERY DIFFERENT interpretations?
3. Would researching the wrong interpretation waste time?

If clarification needed:
1. Ask ONE short question in Dhivehi (ދިވެހި)
2. Provide 2-4 OPTIONS for the user to choose from (for inline buttons)
3. Each option should have a short label (max 30 chars) in Dhivehi
4. Be friendly and explain briefly why you're asking"""

DECOMPOSITION_PROMPT = """You are a research assistant that breaks down complex questions into smaller, focused sub-queries.

Given a user's question, decompose it into 2-5 independent sub-queries that:
1. Each cover a distinct aspect of the original question
2. Are self-contained and independently searchable
3. Together provide comprehensive coverage of the original question
4. Are specific enough to yield focused search results

Even for simple questions, generate at least 2 sub-queries to ensure thorough coverage.

Original question: {question}

Decompose this question into sub-queries."""


class QueryDecomposer:
    """Decomposes complex questions into sub-queries using Gemini."""
    
    def __init__(self, client: genai.Client):
        """Initialize with a Gemini client.
        
        Args:
            client: The Google GenAI client instance
        """
        self.client = client
    
    def check_clarification_needed(
        self, question: str, context: str = ""
    ) -> ClarificationResult:
        """Check if the question needs clarification before research.
        
        Args:
            question: The user's question
            context: Previous conversation context (clarifications already given)
            
        Returns:
            ClarificationResult indicating if clarification is needed
        """
        prompt = CLARIFICATION_PROMPT.format(question=question, context=context or "None")
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClarificationResult,
            system_instruction="You are a helpful assistant that determines if questions need clarification.",
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        response = self.client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt,
            config=config,
        )
        
        return ClarificationResult.model_validate_json(response.text)
    
    def decompose(self, question: str, system_instruction: Optional[str] = None) -> list[SubQuery]:
        """Decompose a question into 2-5 sub-queries using Gemini structured output.
        
        Args:
            question: The user's original question to decompose
            system_instruction: Optional system instruction override
            
        Returns:
            List of SubQuery objects (2-5 items)
            
        Raises:
            ValueError: If decomposition fails or returns invalid count
        """
        prompt = DECOMPOSITION_PROMPT.format(question=question)
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SubQueryList,
            system_instruction=system_instruction or "You are a helpful research assistant.",
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        response = self.client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt,
            config=config,
        )
        
        # Parse the structured response
        result = SubQueryList.model_validate_json(response.text)
        
        # Ensure we have 2-5 sub-queries
        sub_queries = result.sub_queries
        if len(sub_queries) < 2:
            # If less than 2, duplicate with variation
            while len(sub_queries) < 2:
                sub_queries.append(SubQueryItem(
                    query_text=question,
                    aspect="General overview"
                ))
        elif len(sub_queries) > 5:
            # If more than 5, take the first 5
            sub_queries = sub_queries[:5]
        
        # Convert to SubQuery models with unique IDs
        return [
            SubQuery(
                id=f"sq-{uuid.uuid4().hex[:8]}",
                query_text=sq.query_text,
                aspect=sq.aspect
            )
            for sq in sub_queries
        ]
