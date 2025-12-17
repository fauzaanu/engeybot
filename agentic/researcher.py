"""Research engine for executing grounded searches on sub-queries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import httpx
from google import genai
from google.genai import types

from agentic.models import ResearchResult, SourceInfo, SubQuery


# Default system instruction for research queries
RESEARCH_SYSTEM_INSTRUCTION = """You are a research assistant conducting focused research on specific topics.
Provide detailed, factual information based on your search results.
Always cite your sources and provide comprehensive answers."""


class ResearchEngine:
    """Executes grounded searches for sub-queries using Gemini with Google Search."""
    
    def __init__(self, client: genai.Client, system_instruction: Optional[str] = None):
        """Initialize with a Gemini client.
        
        Args:
            client: The Google GenAI client instance
            system_instruction: Optional custom system instruction for research
        """
        self.client = client
        self.system_instruction = system_instruction or RESEARCH_SYSTEM_INSTRUCTION
    
    def research_query(self, sub_query: SubQuery, max_retries: int = 1) -> ResearchResult:
        """Execute a single grounded search with retry logic.
        
        Args:
            sub_query: The sub-query to research
            max_retries: Number of retries on failure (default: 1)
            
        Returns:
            ResearchResult with response text and sources, or error info if failed
        """
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            system_instruction=self.system_instruction,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        last_error: Optional[str] = None
        attempts = 0
        
        while attempts <= max_retries:
            try:
                response = self.client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=sub_query.query_text,
                    config=config,
                )
                
                response_text = response.text.strip() if response.text else ""
                
                # Extract sources from grounding metadata
                sources = self._extract_sources(response)
                
                return ResearchResult(
                    sub_query_id=sub_query.id,
                    response_text=response_text,
                    sources=sources,
                    success=True,
                    error_message=None,
                )
                
            except Exception as e:
                last_error = str(e)
                attempts += 1
        
        # All retries exhausted
        return ResearchResult(
            sub_query_id=sub_query.id,
            response_text="",
            sources=[],
            success=False,
            error_message=f"Research failed after {max_retries + 1} attempts: {last_error}",
        )
    
    def _resolve_redirect_url(self, url: str) -> str:
        """Resolve a redirect URL to get the final destination URL.
        
        Args:
            url: The URL to resolve (may be a redirect URL)
            
        Returns:
            The final destination URL, or the original URL if resolution fails
        """
        if not url or "grounding-api-redirect" not in url:
            return url
        
        try:
            # Use HEAD request with redirect following disabled to get Location header
            with httpx.Client(follow_redirects=False, timeout=5.0) as client:
                response = client.head(url)
                if response.status_code in (301, 302, 303, 307, 308):
                    return response.headers.get("location", url)
        except Exception:
            pass
        
        return url
    
    def _extract_sources(self, response) -> list[SourceInfo]:
        """Extract source information from grounding metadata.
        
        Args:
            response: The Gemini API response
            
        Returns:
            List of SourceInfo objects with title and URL
        """
        sources: list[SourceInfo] = []
        seen_urls: set[str] = set()
        
        try:
            if not response.candidates or not response.candidates[0].grounding_metadata:
                return sources
            
            metadata = response.candidates[0].grounding_metadata
            chunks = getattr(metadata, "grounding_chunks", None) or []
            
            for chunk in chunks:
                if hasattr(chunk, "web") and chunk.web:
                    title = getattr(chunk.web, "title", None) or "Source"
                    raw_url = getattr(chunk.web, "uri", None) or ""
                    
                    # Resolve redirect URLs to get actual destination
                    url = self._resolve_redirect_url(raw_url)
                    
                    # Skip duplicates and empty URLs
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        sources.append(SourceInfo(title=title, url=url))
        
        except Exception:
            # Silently handle extraction errors - sources are optional
            pass
        
        return sources
    
    def research_single(self, question: str, max_retries: int = 1) -> ResearchResult:
        """Execute a single grounded search for a question.
        
        This is the simplified approach - one comprehensive search instead of
        multiple sub-queries.
        
        Args:
            question: The full question to research
            max_retries: Number of retries on failure (default: 1)
            
        Returns:
            ResearchResult with response text and sources
        """
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            system_instruction=self.system_instruction,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        
        last_error: Optional[str] = None
        attempts = 0
        
        while attempts <= max_retries:
            try:
                response = self.client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=question,
                    config=config,
                )
                
                response_text = response.text.strip() if response.text else ""
                sources = self._extract_sources(response)
                
                return ResearchResult(
                    sub_query_id="main",
                    response_text=response_text,
                    sources=sources,
                    success=True,
                    error_message=None,
                )
                
            except Exception as e:
                last_error = str(e)
                attempts += 1
        
        return ResearchResult(
            sub_query_id="main",
            response_text="",
            sources=[],
            success=False,
            error_message=f"Research failed after {max_retries + 1} attempts: {last_error}",
        )
    
    def research_all(
        self,
        sub_queries: list[SubQuery],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[ResearchResult]:
        """Research all sub-queries IN PARALLEL for faster execution.
        
        Args:
            sub_queries: List of sub-queries to research
            on_progress: Optional callback called with (current, total) after each query
            
        Returns:
            List of ResearchResult objects, one for each sub-query (in order)
        """
        total = len(sub_queries)
        completed = 0
        results: list[ResearchResult] = [None] * total  # Pre-allocate to maintain order
        
        def research_with_index(args: tuple[int, SubQuery]) -> tuple[int, ResearchResult]:
            """Research a query and return with its index."""
            idx, sub_query = args
            result = self.research_query(sub_query)
            return idx, result
        
        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=min(total, 5)) as executor:
            # Submit all queries in parallel
            futures = list(executor.map(
                research_with_index,
                enumerate(sub_queries)
            ))
            
            # Process results as they complete
            for idx, result in futures:
                results[idx] = result
                completed += 1
                if on_progress is not None:
                    on_progress(completed, total)
        
        return results
