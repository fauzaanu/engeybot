"""Synthesis engine for combining research results into coherent responses."""

from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from agentic.models import ResearchResult, SourceInfo, SubQuery, SynthesizedResponse


class SynthesisOutput(BaseModel):
    """Structured output for synthesis."""
    response_text: str = Field(description="The synthesized response combining all research")
    sections: list[str] = Field(
        default_factory=list,
        description="Section headings used to structure the response"
    )


SYNTHESIS_PROMPT = """You are a friendly chat assistant. Your task is to summarize research findings into a brief, conversational response.

Original Question: {original_question}

Research Findings:
{research_findings}

Instructions:
1. ALWAYS respond in Dhivehi (ދިވެހި) language
2. Keep your response SHORT - maximum 5-6 lines, like a friend explaining something casually
3. Be conversational and friendly, not formal or article-like
4. Focus on the key points only - don't overwhelm with details
5. No section headings needed - just a simple, direct answer

Remember: This is a chat, not an article. Keep it brief and friendly!"""


class SynthesisEngine:
    """Combines research results into a coherent synthesized response."""
    
    def __init__(self, client: genai.Client):
        """Initialize with a Gemini client.
        
        Args:
            client: The Google GenAI client instance
        """
        self.client = client
    
    def synthesize(
        self,
        original_question: str,
        sub_queries: list[SubQuery],
        results: list[ResearchResult],
    ) -> SynthesizedResponse:
        """Combine all research results into a structured final response.
        
        Args:
            original_question: The user's original question
            sub_queries: List of sub-queries that were researched
            results: List of research results from each sub-query
            
        Returns:
            SynthesizedResponse with combined text, deduplicated sources, and sections
        """
        # Build research findings text for the prompt
        research_findings = self._format_research_findings(sub_queries, results)
        
        # Generate synthesis using Gemini
        prompt = SYNTHESIS_PROMPT.format(
            original_question=original_question,
            research_findings=research_findings,
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SynthesisOutput,
            system_instruction="You are a helpful research synthesis assistant.",
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=config,
        )
        
        # Parse the structured response
        synthesis_output = SynthesisOutput.model_validate_json(response.text)
        
        # Collect and deduplicate sources from all research results
        deduplicated_sources = self._deduplicate_sources(results)
        
        return SynthesizedResponse(
            response_text=synthesis_output.response_text,
            sources=deduplicated_sources,
            sections=synthesis_output.sections,
            follow_up_questions=[],
        )
    
    def _format_research_findings(
        self,
        sub_queries: list[SubQuery],
        results: list[ResearchResult],
    ) -> str:
        """Format research findings for the synthesis prompt.
        
        Args:
            sub_queries: List of sub-queries
            results: List of research results
            
        Returns:
            Formatted string of research findings
        """
        # Create a mapping of sub-query IDs to sub-queries
        query_map = {sq.id: sq for sq in sub_queries}
        
        findings_parts: list[str] = []
        
        for i, result in enumerate(results, start=1):
            sub_query = query_map.get(result.sub_query_id)
            aspect = sub_query.aspect if sub_query else f"Aspect {i}"
            query_text = sub_query.query_text if sub_query else "Unknown query"
            
            if result.success and result.response_text:
                finding = f"""
## Finding {i}: {aspect}
Query: {query_text}
Response: {result.response_text}
"""
                findings_parts.append(finding)
        
        return "\n".join(findings_parts) if findings_parts else "No research findings available."
    
    def _deduplicate_sources(self, results: list[ResearchResult]) -> list[SourceInfo]:
        """Collect and deduplicate sources from all research results.
        
        Args:
            results: List of research results
            
        Returns:
            List of unique SourceInfo objects (deduplicated by URL)
        """
        seen_urls: set[str] = set()
        unique_sources: list[SourceInfo] = []
        
        for result in results:
            for source in result.sources:
                if source.url and source.url not in seen_urls:
                    seen_urls.add(source.url)
                    unique_sources.append(source)
        
        return unique_sources
    
    def summarize(
        self,
        original_question: str,
        research_result: ResearchResult,
    ) -> SynthesizedResponse:
        """Summarize a single research result into a brief response.
        
        This is the simplified approach - takes one research result and
        creates a concise, friendly summary.
        
        Args:
            original_question: The user's original question
            research_result: The research result to summarize
            
        Returns:
            SynthesizedResponse with summary, sources, and follow-up questions
        """
        prompt = SYNTHESIS_PROMPT.format(
            original_question=original_question,
            research_findings=research_result.response_text,
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SynthesisOutput,
            system_instruction="You are a helpful research synthesis assistant.",
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=config,
        )
        
        synthesis_output = SynthesisOutput.model_validate_json(response.text)
        
        return SynthesizedResponse(
            response_text=synthesis_output.response_text,
            sources=research_result.sources,
            sections=synthesis_output.sections,
            follow_up_questions=[],
        )
