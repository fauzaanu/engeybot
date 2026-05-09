"""Handler for Telegram Bot API 10.0 Guest Mode (answerGuestQuery).

Guest mode allows bots to receive messages and reply in chats they are not
a member of. When a user @mentions the bot in any chat, the bot receives a
`guest_message` update containing the message with a `guest_query_id`. The bot
must respond using the `answerGuestQuery` method, which takes an InlineQueryResult.

Since pyTelegramBotAPI hasn't implemented Bot API 10.0 yet, this module provides:
- Direct HTTP calls to the answerGuestQuery endpoint
- Update parsing for the guest_message field
- Integration with the existing agentic pipeline for generating responses
"""

import json
import traceback
from typing import Optional

import httpx
from google import genai

from config import BOT_TOKEN, GEMINI_API_KEY, SYSTEM_INSTRUCTION

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Gemini client for generating responses to guest queries
_gemini_client = genai.Client(api_key=GEMINI_API_KEY)


class SentGuestMessage:
    """Represents the response from answerGuestQuery.

    Attributes:
        inline_message_id: Identifier of the sent inline message.
    """

    def __init__(self, inline_message_id: str):
        self.inline_message_id = inline_message_id

    @classmethod
    def from_dict(cls, data: dict) -> "SentGuestMessage":
        return cls(inline_message_id=data.get("inline_message_id", ""))


def answer_guest_query(
    guest_query_id: str,
    result: dict,
) -> Optional[SentGuestMessage]:
    """Call the Telegram answerGuestQuery method.

    Args:
        guest_query_id: Unique identifier for the guest query (from Message.guest_query_id).
        result: A JSON-serializable dict representing an InlineQueryResult object.

    Returns:
        SentGuestMessage on success, None on failure.
    """
    payload = {
        "guest_query_id": guest_query_id,
        "result": json.dumps(result),
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{TELEGRAM_API_BASE}/answerGuestQuery",
                json=payload,
            )
            response_data = response.json()

            if response_data.get("ok"):
                return SentGuestMessage.from_dict(response_data.get("result", {}))
            else:
                print(
                    f"answerGuestQuery failed: {response_data.get('description', 'Unknown error')}"
                )
                return None
    except Exception as e:
        print(f"answerGuestQuery request failed: {e}")
        traceback.print_exc()
        return None


def build_text_result(
    result_id: str,
    title: str,
    message_text: str,
    parse_mode: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Build an InlineQueryResultArticle dict for answerGuestQuery.

    Args:
        result_id: Unique identifier for this result.
        title: Title of the result.
        message_text: Text of the message to be sent.
        parse_mode: Optional parse mode (Markdown, HTML).
        description: Optional short description of the result.

    Returns:
        Dict representing an InlineQueryResultArticle.
    """
    input_message_content = {"message_text": message_text}
    if parse_mode:
        input_message_content["parse_mode"] = parse_mode

    result = {
        "type": "article",
        "id": result_id,
        "title": title,
        "input_message_content": input_message_content,
    }
    if description:
        result["description"] = description

    return result


def generate_guest_response(text: str) -> str:
    """Generate a response for a guest query using Gemini.

    Uses grounded search to provide informative answers.

    Args:
        text: The message text from the guest query.

    Returns:
        Generated response text.
    """
    from google.genai import types

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        system_instruction=SYSTEM_INSTRUCTION
        + "\nYou are responding to a guest query in a Telegram chat. Keep your response concise but informative.",
    )

    try:
        response = _gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=text,
            config=config,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Guest response generation failed: {e}")
        return "Sorry, I couldn't process that request."


def handle_guest_message(update_data: dict) -> bool:
    """Process a guest_message from a raw update dict.

    This should be called when processing webhook updates that contain
    the `guest_message` field.

    Args:
        update_data: The raw update JSON dict from Telegram.

    Returns:
        True if the update was handled as a guest message, False otherwise.
    """
    guest_message = update_data.get("guest_message")
    if not guest_message:
        return False

    guest_query_id = guest_message.get("guest_query_id")
    if not guest_query_id:
        print("Guest message received but no guest_query_id found")
        return False

    # Extract the text content
    text = guest_message.get("text", "")
    if not text:
        # Try caption for media messages
        text = guest_message.get("caption", "")

    if not text:
        # Can't process without text
        answer_guest_query(
            guest_query_id,
            build_text_result(
                result_id="guest_no_text",
                title="Response",
                message_text="I can only respond to text messages in guest mode.",
            ),
        )
        return True

    # Extract caller info for logging
    caller_user = guest_message.get("guest_bot_caller_user", {})
    caller_chat = guest_message.get("guest_bot_caller_chat", {})
    caller_name = caller_user.get("first_name", "Unknown")
    chat_title = caller_chat.get("title", caller_chat.get("first_name", "Unknown chat"))

    print(f"Guest query from {caller_name} in {chat_title}: {text[:80]}...")

    # Remove bot mention from text if present
    # Guest messages typically include the @bot_username mention
    from main import BOT_USERNAME

    clean_text = text.replace(BOT_USERNAME, "").replace(BOT_USERNAME.lower(), "").strip()
    if not clean_text:
        clean_text = text  # Fallback to original if stripping removed everything

    # Generate response
    response_text = generate_guest_response(clean_text)

    # Send the response via answerGuestQuery
    import uuid

    result = build_text_result(
        result_id=f"guest_{uuid.uuid4().hex[:12]}",
        title="Response",
        message_text=response_text,
        description=response_text[:100] if len(response_text) > 100 else None,
    )

    sent = answer_guest_query(guest_query_id, result)
    if sent:
        print(f"Guest query answered successfully (inline_message_id: {sent.inline_message_id})")
    else:
        print("Failed to answer guest query")

    return True
