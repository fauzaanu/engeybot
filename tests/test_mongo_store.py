"""Property-based tests for MongoDB store operations."""

from datetime import datetime
from unittest.mock import patch

import mongomock
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
from agentic.mongo_store import MongoStore


# Strategies for generating test data (reused from test_models.py)
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


@pytest.fixture
def mongo_store():
    """Create a MongoStore with a mocked MongoDB client."""
    with patch("agentic.mongo_store.MongoClient", mongomock.MongoClient):
        store = MongoStore("mongodb://localhost:27017", "test_db")
        yield store
        # Clean up after each test
        store.conversations.drop()



# **Feature: agentic-chat, Property 9: Conversation Creation Completeness**
# **Validates: Requirements 5.1**
@given(conversation_state_strategy)
@settings(max_examples=100)
def test_conversation_creation_completeness(state: ConversationState):
    """
    Property 9: Conversation Creation Completeness

    For any ConversationState created via MongoDB_Store.create_conversation,
    the stored document SHALL contain non-null values for id, user_id, chat_id,
    original_question, and created_at.
    """
    with patch("agentic.mongo_store.MongoClient", mongomock.MongoClient):
        store = MongoStore("mongodb://localhost:27017", "test_db")
        try:
            # Create the conversation
            returned_id = store.create_conversation(state)

            # Verify the returned ID matches
            assert returned_id == state.id

            # Retrieve the stored document directly
            doc = store.conversations.find_one({"id": state.id})

            # Verify required fields are non-null
            assert doc is not None, "Document should exist after creation"
            assert doc.get("id") is not None, "id should be non-null"
            assert doc.get("user_id") is not None, "user_id should be non-null"
            assert doc.get("chat_id") is not None, "chat_id should be non-null"
            assert doc.get("original_question") is not None, "original_question should be non-null"
            assert doc.get("created_at") is not None, "created_at should be non-null"
        finally:
            store.conversations.drop()



# **Feature: agentic-chat, Property 10: Sub-Query Persistence**
# **Validates: Requirements 5.2**
@given(
    conversation_state_strategy,
    st.lists(sub_query_strategy, min_size=1, max_size=5)
)
@settings(max_examples=100)
def test_sub_query_persistence(state: ConversationState, sub_queries: list[SubQuery]):
    """
    Property 10: Sub-Query Persistence

    For any conversation where sub-queries are generated, after calling
    update_conversation with sub_queries, retrieving the conversation SHALL
    return a ConversationState with the same sub-queries.
    """
    with patch("agentic.mongo_store.MongoClient", mongomock.MongoClient):
        store = MongoStore("mongodb://localhost:27017", "test_db")
        try:
            # Create initial conversation
            store.create_conversation(state)

            # Update with sub-queries
            sub_queries_data = [sq.model_dump(mode="json") for sq in sub_queries]
            store.update_conversation(state.id, {"sub_queries": sub_queries_data})

            # Retrieve and verify
            retrieved = store.get_conversation(state.id)
            assert retrieved is not None, "Conversation should be retrievable"
            assert len(retrieved.sub_queries) == len(sub_queries)
            for original, retrieved_sq in zip(sub_queries, retrieved.sub_queries):
                assert retrieved_sq == original
        finally:
            store.conversations.drop()


# **Feature: agentic-chat, Property 11: Research Result Persistence**
# **Validates: Requirements 5.3**
@given(
    conversation_state_strategy,
    st.lists(research_result_strategy, min_size=1, max_size=5)
)
@settings(max_examples=100)
def test_research_result_persistence(state: ConversationState, research_results: list[ResearchResult]):
    """
    Property 11: Research Result Persistence

    For any conversation where research is completed, after calling
    update_conversation with research_results, retrieving the conversation
    SHALL return a ConversationState with the same research results.
    """
    with patch("agentic.mongo_store.MongoClient", mongomock.MongoClient):
        store = MongoStore("mongodb://localhost:27017", "test_db")
        try:
            # Create initial conversation
            store.create_conversation(state)

            # Update with research results
            results_data = [rr.model_dump(mode="json") for rr in research_results]
            store.update_conversation(state.id, {"research_results": results_data})

            # Retrieve and verify
            retrieved = store.get_conversation(state.id)
            assert retrieved is not None, "Conversation should be retrievable"
            assert len(retrieved.research_results) == len(research_results)
            for original, retrieved_rr in zip(research_results, retrieved.research_results):
                assert retrieved_rr == original
        finally:
            store.conversations.drop()


# **Feature: agentic-chat, Property 12: Final Response Persistence**
# **Validates: Requirements 5.4**
@given(
    conversation_state_strategy,
    synthesized_response_strategy,
    st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
)
@settings(max_examples=100)
def test_final_response_persistence(
    state: ConversationState,
    final_response: SynthesizedResponse,
    completed_at: datetime
):
    """
    Property 12: Final Response Persistence

    For any conversation where synthesis is completed, after calling
    update_conversation with final_response and completed_at, retrieving
    the conversation SHALL return a ConversationState with matching
    final_response and a non-null completed_at.
    """
    with patch("agentic.mongo_store.MongoClient", mongomock.MongoClient):
        store = MongoStore("mongodb://localhost:27017", "test_db")
        try:
            # Create initial conversation
            store.create_conversation(state)

            # Update with final response and completion time
            store.update_conversation(state.id, {
                "final_response": final_response.model_dump(mode="json"),
                "completed_at": completed_at.isoformat()
            })

            # Retrieve and verify
            retrieved = store.get_conversation(state.id)
            assert retrieved is not None, "Conversation should be retrievable"
            assert retrieved.final_response is not None, "final_response should be set"
            assert retrieved.final_response == final_response
            assert retrieved.completed_at is not None, "completed_at should be non-null"
        finally:
            store.conversations.drop()
