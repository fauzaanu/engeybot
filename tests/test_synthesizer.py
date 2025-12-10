"""Property-based tests for synthesis engine."""

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from agentic.models import ResearchResult, SourceInfo, SubQuery, SynthesizedResponse
from agentic.synthesizer import SynthesisEngine, SynthesisOutput


# Strategy for generating valid SubQuery objects
sub_query_strategy = st.builds(
    SubQuery,
    id=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))).map(lambda x: f"sq-{x}"),
    query_text=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    aspect=st.text(min_size=3, max_size=100).filter(lambda x: x.strip()),
)

# Strategy for generating source info
source_info_strategy = st.builds(
    SourceInfo,
    title=st.text(min_size=3, max_size=100).filter(lambda x: x.strip()),
    url=st.from_regex(r"https://[a-z]+\.[a-z]+/[a-z0-9]+", fullmatch=True),
)

# Strategy for generating response text (non-empty)
response_text_strategy = st.text(min_size=10, max_size=500).filter(lambda x: x.strip())

# Strategy for generating section headings
section_strategy = st.text(min_size=3, max_size=50).filter(lambda x: x.strip())


def create_research_result(sub_query_id: str, response_text: str, sources: list[SourceInfo]) -> ResearchResult:
    """Create a successful research result."""
    return ResearchResult(
        sub_query_id=sub_query_id,
        response_text=response_text,
        sources=sources,
        success=True,
        error_message=None,
    )


def create_mock_client_for_synthesis(
    response_text: str,
    sections: list[str],
) -> MagicMock:
    """Create a mock Gemini client that returns synthesis results.
    
    Args:
        response_text: The synthesized response text to return
        sections: List of section headings to return
    """
    mock_client = MagicMock()
    
    # Build mock response with structured output
    synthesis_output = SynthesisOutput(
        response_text=response_text,
        sections=sections,
    )
    
    mock_response = MagicMock()
    mock_response.text = synthesis_output.model_dump_json()
    mock_client.models.generate_content.return_value = mock_response
    
    return mock_client


# Strategy for generating a list of sub-queries with matching research results
@st.composite
def sub_queries_with_results_strategy(draw):
    """Generate sub-queries with matching research results (non-empty list)."""
    # Generate 1-5 sub-queries
    num_queries = draw(st.integers(min_value=1, max_value=5))
    
    sub_queries = []
    results = []
    
    for i in range(num_queries):
        sq = draw(sub_query_strategy)
        sub_queries.append(sq)
        
        # Generate response text and sources for this result
        resp_text = draw(response_text_strategy)
        sources = draw(st.lists(source_info_strategy, min_size=0, max_size=3))
        
        result = create_research_result(sq.id, resp_text, sources)
        results.append(result)
    
    return sub_queries, results


# Strategy for generating at least 2 sub-queries with results (for section test)
@st.composite
def multiple_sub_queries_with_results_strategy(draw):
    """Generate at least 2 sub-queries with matching research results."""
    # Generate 2-5 sub-queries
    num_queries = draw(st.integers(min_value=2, max_value=5))
    
    sub_queries = []
    results = []
    
    for i in range(num_queries):
        sq = draw(sub_query_strategy)
        sub_queries.append(sq)
        
        # Generate response text and sources for this result
        resp_text = draw(response_text_strategy)
        sources = draw(st.lists(source_info_strategy, min_size=0, max_size=3))
        
        result = create_research_result(sq.id, resp_text, sources)
        results.append(result)
    
    return sub_queries, results


# **Feature: agentic-chat, Property 6: Synthesis Produces Output**
# **Validates: Requirements 4.1**
@given(
    data=sub_queries_with_results_strategy(),
    question=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    synth_response=response_text_strategy,
)
@settings(max_examples=100)
def test_synthesis_produces_output(
    data: tuple[list[SubQuery], list[ResearchResult]],
    question: str,
    synth_response: str,
):
    """
    Property 6: Synthesis Produces Output
    
    For any non-empty list of ResearchResults passed to the SynthesisEngine, 
    the resulting SynthesizedResponse SHALL have a non-empty response_text.
    """
    sub_queries, results = data
    
    # Create mock client that returns the generated response
    mock_client = create_mock_client_for_synthesis(synth_response, ["Section 1"])
    
    engine = SynthesisEngine(mock_client)
    response = engine.synthesize(question, sub_queries, results)
    
    # Verify the response has non-empty text
    assert isinstance(response, SynthesizedResponse)
    assert len(response.response_text) > 0, (
        "Synthesis must produce non-empty response_text"
    )


# **Feature: agentic-chat, Property 7: Source Preservation**
# **Validates: Requirements 4.2**
@given(
    data=sub_queries_with_results_strategy(),
    question=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    synth_response=response_text_strategy,
)
@settings(max_examples=100)
def test_source_preservation(
    data: tuple[list[SubQuery], list[ResearchResult]],
    question: str,
    synth_response: str,
):
    """
    Property 7: Source Preservation
    
    For any synthesis operation, the sources in the SynthesizedResponse SHALL 
    be a subset of the union of all sources from the input ResearchResults.
    """
    sub_queries, results = data
    
    # Create mock client
    mock_client = create_mock_client_for_synthesis(synth_response, ["Section 1"])
    
    engine = SynthesisEngine(mock_client)
    response = engine.synthesize(question, sub_queries, results)
    
    # Collect all source URLs from input results
    all_input_urls = set()
    for result in results:
        for source in result.sources:
            all_input_urls.add(source.url)
    
    # Verify all output sources are from the input
    for source in response.sources:
        assert source.url in all_input_urls, (
            f"Source URL {source.url} not found in input research results"
        )


# **Feature: agentic-chat, Property 8: Synthesis Has Sections**
# **Validates: Requirements 4.3**
@given(
    data=multiple_sub_queries_with_results_strategy(),
    question=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    synth_response=response_text_strategy,
    sections=st.lists(section_strategy, min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_synthesis_has_sections(
    data: tuple[list[SubQuery], list[ResearchResult]],
    question: str,
    synth_response: str,
    sections: list[str],
):
    """
    Property 8: Synthesis Has Sections
    
    For any synthesis operation with at least 2 research results, the 
    SynthesizedResponse SHALL have at least 1 section in the sections list.
    """
    sub_queries, results = data
    
    # Ensure we have at least 2 results (strategy guarantees this)
    assert len(results) >= 2, "Test requires at least 2 research results"
    
    # Create mock client that returns sections
    mock_client = create_mock_client_for_synthesis(synth_response, sections)
    
    engine = SynthesisEngine(mock_client)
    response = engine.synthesize(question, sub_queries, results)
    
    # Verify the response has at least 1 section
    assert len(response.sections) >= 1, (
        f"Synthesis with {len(results)} results must have at least 1 section, "
        f"got {len(response.sections)}"
    )
