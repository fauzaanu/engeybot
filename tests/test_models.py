"""Property-based tests for agentic chat models."""

from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic.models import (
    ConversationState,
    ProcessingStage,
    ResearchResult,
    SourceInfo,
    SubQuery,
    SynthesizedResponse,
)


# Strategies for generating test data
source_info_strategy = st.builds(
    SourceInfo,
    title=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    url=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
)

sub_query_strategy = st.builds(
    SubQuery,
    id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    query_text=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
    aspect=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
)

research_result_strategy = st.builds(
    ResearchResult,
    sub_query_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    response_text=st.text(min_size=1, max_size=1000).filter(lambda x: x.strip()),
    sources=st.lists(source_info_strategy, min_size=0, max_size=5),
    success=st.booleans(),
    error_message=st.one_of(st.none(), st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
)

synthesized_response_strategy = st.builds(
    SynthesizedResponse,
    response_text=st.text(min_size=1, max_size=2000).filter(lambda x: x.strip()),
    sources=st.lists(source_info_strategy, min_size=0, max_size=10),
    sections=st.lists(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()), min_size=0, max_size=5),
)

conversation_state_strategy = st.builds(
    ConversationState,
    id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    user_id=st.integers(min_value=1, max_value=2**31),
    chat_id=st.integers(min_value=-2**31, max_value=2**31),
    message_id=st.integers(min_value=1, max_value=2**31),
    status_message_id=st.one_of(st.none(), st.integers(min_value=1, max_value=2**31)),
    original_question=st.text(min_size=1, max_size=1000).filter(lambda x: x.strip()),
    stage=st.sampled_from(list(ProcessingStage)),
    sub_queries=st.lists(sub_query_strategy, min_size=0, max_size=5),
    research_results=st.lists(research_result_strategy, min_size=0, max_size=5),
    final_response=st.one_of(st.none(), synthesized_response_strategy),
    created_at=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
    completed_at=st.one_of(st.none(), st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))),
    error_message=st.one_of(st.none(), st.text(min_size=1, max_size=500).filter(lambda x: x.strip())),
)


# **Feature: agentic-chat, Property 13: Pydantic Model Round-Trip**
# **Validates: Requirements 5.5**
@given(conversation_state_strategy)
@settings(max_examples=100)
def test_conversation_state_round_trip(state: ConversationState):
    """
    Property 13: Pydantic Model Round-Trip
    
    For any valid ConversationState, serializing to JSON via model_dump_json()
    and deserializing via model_validate_json() SHALL produce an equivalent ConversationState.
    """
    # Serialize to JSON
    json_str = state.model_dump_json()
    
    # Deserialize back
    restored = ConversationState.model_validate_json(json_str)
    
    # Verify equivalence
    assert restored == state


# **Feature: agentic-chat, Property 14: Source Hyperlink Formatting**
# **Validates: Requirements 4.5**
@given(source_info_strategy)
@settings(max_examples=100)
def test_source_hyperlink_formatting(source: SourceInfo):
    """
    Property 14: Source Hyperlink Formatting
    
    For any SourceInfo with a title and URL, when rendered for Telegram display,
    the output SHALL be an HTML hyperlink where the visible text is the title
    and the href attribute contains the full URL.
    """
    html_output = source.to_html()
    
    # Verify it's an HTML anchor tag
    assert html_output.startswith('<a href="')
    assert html_output.endswith('</a>')
    
    # Verify the URL is in the href attribute
    assert f'href="{source.url}"' in html_output
    
    # Verify the title is the visible text (between > and </a>)
    assert f'>{source.title}</a>' in html_output
