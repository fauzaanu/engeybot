"""Property-based tests for query decomposer."""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic.decomposer import QueryDecomposer, SubQueryList, SubQueryItem
from agentic.models import SubQuery


# Strategy for generating valid questions
question_strategy = st.text(min_size=5, max_size=500).filter(
    lambda x: x.strip() and not x.isspace()
)

# Strategy for generating sub-query items (what Gemini would return)
sub_query_item_strategy = st.builds(
    SubQueryItem,
    query_text=st.text(min_size=5, max_size=200).filter(lambda x: x.strip()),
    aspect=st.text(min_size=3, max_size=100).filter(lambda x: x.strip()),
)

# Strategy for generating valid SubQueryList responses (2-5 items)
# Note: SubQueryList has Pydantic validation (min_length=2, max_length=5)
# which means Gemini's structured output will always return valid counts
valid_sub_query_list_strategy = st.builds(
    SubQueryList,
    sub_queries=st.lists(sub_query_item_strategy, min_size=2, max_size=5),
    reasoning=st.text(min_size=10, max_size=300).filter(lambda x: x.strip()),
)


def create_mock_client(response_json: str) -> MagicMock:
    """Create a mock Gemini client that returns the given JSON response."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_json
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


# **Feature: agentic-chat, Property 2: Sub-Query Count Bounds**
# **Validates: Requirements 2.1**
@given(question=question_strategy, sub_query_list=valid_sub_query_list_strategy)
@settings(max_examples=100)
def test_sub_query_count_bounds(question: str, sub_query_list: SubQueryList):
    """
    Property 2: Sub-Query Count Bounds
    
    For any user question processed by the QueryDecomposer, the number of 
    generated sub-queries SHALL be between 2 and 5 inclusive.
    
    The SubQueryList Pydantic model enforces min_length=2 and max_length=5
    on the sub_queries field, which means Gemini's structured output will
    always return a valid count. This test verifies that the decomposer
    correctly processes these responses and maintains the count bounds.
    """
    # Create mock client with the generated response
    mock_client = create_mock_client(sub_query_list.model_dump_json())
    
    decomposer = QueryDecomposer(mock_client)
    result = decomposer.decompose(question)
    
    # Verify the count is within bounds
    assert 2 <= len(result) <= 5, f"Expected 2-5 sub-queries, got {len(result)}"
    
    # Verify all results are SubQuery instances with proper structure
    for sq in result:
        assert isinstance(sq, SubQuery)
        assert sq.id.startswith("sq-")
        assert len(sq.query_text) > 0
        assert len(sq.aspect) > 0
    
    # Verify the count matches the input (since Pydantic enforces bounds)
    assert len(result) == len(sub_query_list.sub_queries)
