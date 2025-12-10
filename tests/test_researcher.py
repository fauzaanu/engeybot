"""Property-based tests for research engine."""

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from agentic.models import ResearchResult, SourceInfo, SubQuery
from agentic.researcher import ResearchEngine


# Strategy for generating valid SubQuery objects
sub_query_strategy = st.builds(
    SubQuery,
    id=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))).map(lambda x: f"sq-{x}"),
    query_text=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    aspect=st.text(min_size=3, max_size=100).filter(lambda x: x.strip()),
)

# Strategy for generating lists of sub-queries (1-10 items)
sub_query_list_strategy = st.lists(sub_query_strategy, min_size=1, max_size=10)

# Strategy for generating source info
source_info_strategy = st.builds(
    SourceInfo,
    title=st.text(min_size=3, max_size=100).filter(lambda x: x.strip()),
    url=st.from_regex(r"https://[a-z]+\.[a-z]+/[a-z0-9]+", fullmatch=True),
)

# Strategy for generating response text
response_text_strategy = st.text(min_size=10, max_size=500).filter(lambda x: x.strip())


def create_mock_client_for_research(
    response_text: str,
    sources: list[SourceInfo],
    should_fail: bool = False,
) -> MagicMock:
    """Create a mock Gemini client that returns research results.
    
    Args:
        response_text: The text response to return
        sources: List of sources to include in grounding metadata
        should_fail: If True, raise an exception instead
    """
    mock_client = MagicMock()
    
    if should_fail:
        mock_client.models.generate_content.side_effect = Exception("API Error")
        return mock_client
    
    # Build mock response with grounding metadata
    mock_response = MagicMock()
    mock_response.text = response_text
    
    # Build grounding chunks
    mock_chunks = []
    for source in sources:
        mock_chunk = MagicMock()
        mock_chunk.web = MagicMock()
        mock_chunk.web.title = source.title
        mock_chunk.web.uri = source.url
        mock_chunks.append(mock_chunk)
    
    # Build grounding metadata
    mock_metadata = MagicMock()
    mock_metadata.grounding_chunks = mock_chunks
    
    # Build candidate
    mock_candidate = MagicMock()
    mock_candidate.grounding_metadata = mock_metadata
    
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response
    
    return mock_client


# **Feature: agentic-chat, Property 3: Research Coverage**
# **Validates: Requirements 3.1**
@given(sub_queries=sub_query_list_strategy, response_text=response_text_strategy)
@settings(max_examples=100)
def test_research_coverage(sub_queries: list[SubQuery], response_text: str):
    """
    Property 3: Research Coverage
    
    For any list of sub-queries passed to the ResearchEngine, the number of 
    ResearchResult objects returned SHALL equal the number of input sub-queries.
    """
    # Create mock client that returns successful responses
    mock_client = create_mock_client_for_research(response_text, [])
    
    engine = ResearchEngine(mock_client)
    results = engine.research_all(sub_queries)
    
    # Verify the count matches
    assert len(results) == len(sub_queries), (
        f"Expected {len(sub_queries)} results, got {len(results)}"
    )
    
    # Verify each result corresponds to a sub-query
    result_ids = {r.sub_query_id for r in results}
    query_ids = {sq.id for sq in sub_queries}
    assert result_ids == query_ids, "Result IDs should match sub-query IDs"


# **Feature: agentic-chat, Property 4: Research Result Completeness**
# **Validates: Requirements 3.2**
@given(sub_query=sub_query_strategy, response_text=response_text_strategy)
@settings(max_examples=100)
def test_research_result_completeness(sub_query: SubQuery, response_text: str):
    """
    Property 4: Research Result Completeness
    
    For any successful ResearchResult (where success=True), the response_text 
    field SHALL be non-empty.
    """
    # Create mock client that returns successful response
    mock_client = create_mock_client_for_research(response_text, [])
    
    engine = ResearchEngine(mock_client)
    result = engine.research_query(sub_query)
    
    # If successful, response_text must be non-empty
    if result.success:
        assert len(result.response_text) > 0, (
            "Successful research result must have non-empty response_text"
        )


# **Feature: agentic-chat, Property 5: Progress Callback Correctness**
# **Validates: Requirements 3.4**
@given(sub_queries=sub_query_list_strategy, response_text=response_text_strategy)
@settings(max_examples=100)
def test_progress_callback_correctness(sub_queries: list[SubQuery], response_text: str):
    """
    Property 5: Progress Callback Correctness
    
    For any research_all operation with N sub-queries and a progress callback, 
    the callback SHALL be invoked N times with (current, total) where current 
    ranges from 1 to N and total equals N.
    """
    # Create mock client
    mock_client = create_mock_client_for_research(response_text, [])
    
    # Track callback invocations
    callback_calls: list[tuple[int, int]] = []
    
    def progress_callback(current: int, total: int) -> None:
        callback_calls.append((current, total))
    
    engine = ResearchEngine(mock_client)
    engine.research_all(sub_queries, on_progress=progress_callback)
    
    n = len(sub_queries)
    
    # Verify callback was called N times
    assert len(callback_calls) == n, (
        f"Expected {n} callback invocations, got {len(callback_calls)}"
    )
    
    # Verify current ranges from 1 to N
    expected_currents = list(range(1, n + 1))
    actual_currents = [call[0] for call in callback_calls]
    assert actual_currents == expected_currents, (
        f"Expected current values {expected_currents}, got {actual_currents}"
    )
    
    # Verify total equals N for all calls
    for current, total in callback_calls:
        assert total == n, f"Expected total={n}, got total={total}"
