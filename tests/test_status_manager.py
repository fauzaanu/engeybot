"""Property-based tests for StatusManager."""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic.models import ProcessingStage
from agentic.status_manager import (
    AUTO_DELETE_DURATION,
    STAGE_MESSAGES,
    StatusManager,
    format_sources_html,
    get_stage_message,
)


# **Feature: agentic-chat, Property 1: Stage-Status Consistency**
# **Validates: Requirements 1.2, 1.3**
@given(
    stage=st.sampled_from(list(ProcessingStage)),
    progress=st.text(min_size=0, max_size=20),
)
@settings(max_examples=100)
def test_stage_status_consistency(stage: ProcessingStage, progress: str):
    """
    Property 1: Stage-Status Consistency
    
    For any conversation processing flow, when the Agentic_System transitions
    to a new ProcessingStage, the status message content SHALL reflect that stage name.
    """
    # Get the message for this stage
    message = get_stage_message(stage, progress)
    
    # The message should contain the stage's display text
    stage_text = STAGE_MESSAGES[stage]
    assert stage_text in message, f"Stage text '{stage_text}' not found in message '{message}'"
    
    # If progress is provided and non-empty, it should be in the message
    if progress.strip():
        assert progress in message, f"Progress '{progress}' not found in message '{message}'"


# **Feature: agentic-chat, Property 1: Stage-Status Consistency (via StatusManager)**
# **Validates: Requirements 1.2, 1.3**
@given(
    stage=st.sampled_from(list(ProcessingStage)),
    progress=st.text(min_size=0, max_size=20),
    chat_id=st.integers(min_value=1, max_value=2**31),
    message_id=st.integers(min_value=1, max_value=2**31),
)
@settings(max_examples=100)
def test_status_manager_update_reflects_stage(
    stage: ProcessingStage,
    progress: str,
    chat_id: int,
    message_id: int,
):
    """
    Property 1: Stage-Status Consistency (via StatusManager.update_status)
    
    When StatusManager.update_status is called with a stage, the message
    text passed to edit_message_text SHALL contain the stage's display text.
    """
    # Create mock bot
    mock_bot = MagicMock()
    
    # Create StatusManager without Huey (no auto-delete scheduling)
    manager = StatusManager(mock_bot, huey=None)
    
    # Call update_status
    manager.update_status(chat_id, message_id, stage, progress)
    
    # Verify edit_message_text was called
    mock_bot.edit_message_text.assert_called_once()
    
    # Get the text that was passed
    call_args = mock_bot.edit_message_text.call_args
    text = call_args[0][0]  # First positional argument
    
    # Verify the stage text is in the message
    stage_text = STAGE_MESSAGES[stage]
    assert stage_text in text, f"Stage text '{stage_text}' not found in message '{text}'"
    
    # If progress is provided and non-empty, it should be in the message
    if progress.strip():
        assert progress in text, f"Progress '{progress}' not found in message '{text}'"


# **Feature: agentic-chat, Property 15: Auto-Delete Scheduling**
# **Validates: Requirements 8.1, 8.2**
@given(
    chat_id=st.integers(min_value=1, max_value=2**31),
    message_id=st.integers(min_value=1, max_value=2**31),
    reply_to=st.integers(min_value=1, max_value=2**31),
    text=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
)
@settings(max_examples=100)
def test_auto_delete_scheduling(chat_id: int, message_id: int, reply_to: int, text: str):
    """
    Property 15: Auto-Delete Scheduling
    
    For any message sent by the StatusManager, a deletion task SHALL be
    scheduled for exactly 24 hours (86400 seconds) after the message is sent.
    """
    # Create mock bot that returns a message with the given message_id
    mock_bot = MagicMock()
    mock_message = MagicMock()
    mock_message.message_id = message_id
    mock_bot.send_message.return_value = mock_message
    
    # Create mock Huey with a mock task
    mock_huey = MagicMock()
    mock_task = MagicMock()
    mock_huey.task.return_value = lambda f: mock_task
    
    # Create StatusManager with mock Huey
    manager = StatusManager(mock_bot, huey=mock_huey)
    
    # Manually set the delete task to our mock
    manager._delete_task = mock_task
    
    # Call send_with_auto_delete
    result_id = manager.send_with_auto_delete(chat_id, text, reply_to=reply_to)
    
    # Verify the message was sent
    mock_bot.send_message.assert_called_once()
    assert result_id == message_id
    
    # Verify the deletion task was scheduled with correct delay
    mock_task.schedule.assert_called_once()
    call_args = mock_task.schedule.call_args
    
    # Check the arguments passed to schedule
    scheduled_args = call_args[0][0]  # First positional arg is the tuple (chat_id, message_id)
    scheduled_delay = call_args[1]['delay']  # delay is a keyword argument
    
    assert scheduled_args == (chat_id, message_id), f"Expected ({chat_id}, {message_id}), got {scheduled_args}"
    assert scheduled_delay == AUTO_DELETE_DURATION, f"Expected delay {AUTO_DELETE_DURATION}, got {scheduled_delay}"


# **Feature: agentic-chat, Property 15: Auto-Delete Scheduling (send_initial_status)**
# **Validates: Requirements 8.1, 8.2**
@given(
    chat_id=st.integers(min_value=1, max_value=2**31),
    message_id=st.integers(min_value=1, max_value=2**31),
    reply_to=st.integers(min_value=1, max_value=2**31),
)
@settings(max_examples=100)
def test_auto_delete_scheduling_initial_status(chat_id: int, message_id: int, reply_to: int):
    """
    Property 15: Auto-Delete Scheduling (via send_initial_status)
    
    For any initial status message sent by the StatusManager, a deletion task
    SHALL be scheduled for exactly 24 hours (86400 seconds) after the message is sent.
    """
    # Create mock bot that returns a message with the given message_id
    mock_bot = MagicMock()
    mock_message = MagicMock()
    mock_message.message_id = message_id
    mock_bot.send_message.return_value = mock_message
    
    # Create mock Huey with a mock task
    mock_huey = MagicMock()
    mock_task = MagicMock()
    mock_huey.task.return_value = lambda f: mock_task
    
    # Create StatusManager with mock Huey
    manager = StatusManager(mock_bot, huey=mock_huey)
    
    # Manually set the delete task to our mock
    manager._delete_task = mock_task
    
    # Call send_initial_status
    result_id = manager.send_initial_status(chat_id, reply_to)
    
    # Verify the message was sent
    mock_bot.send_message.assert_called_once()
    assert result_id == message_id
    
    # Verify the deletion task was scheduled with correct delay
    mock_task.schedule.assert_called_once()
    call_args = mock_task.schedule.call_args
    
    # Check the arguments passed to schedule
    scheduled_args = call_args[0][0]  # First positional arg is the tuple (chat_id, message_id)
    scheduled_delay = call_args[1]['delay']  # delay is a keyword argument
    
    assert scheduled_args == (chat_id, message_id), f"Expected ({chat_id}, {message_id}), got {scheduled_args}"
    assert scheduled_delay == AUTO_DELETE_DURATION, f"Expected delay {AUTO_DELETE_DURATION}, got {scheduled_delay}"
