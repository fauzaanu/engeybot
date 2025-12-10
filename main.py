"""Telegram bot with Gemini grounding and image generation."""

import io
import sys
import traceback
import telebot
from google import genai
from huey import RedisHuey

from config import (
    BOT_TOKEN,
    ALLOWED_USERS,
    MODE,
    WEBHOOK_URL,
    GEMINI_API_KEY,
    MONGODB_URI,
    MONGODB_DATABASE,
    REDIS_URL,
)
from router import route_message, RouteType
from generators import generate_grounded_response, generate_simple_response, generate_image_response
from agentic.handler import AgenticHandler
from agentic.mongo_store import MongoStore

bot = telebot.TeleBot(BOT_TOKEN)
MAX_MESSAGE_LENGTH = 4096

# Initialize Gemini client for agentic handler
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize MongoDB store for conversation persistence
mongo_store = MongoStore(MONGODB_URI, MONGODB_DATABASE)

# Initialize Huey for scheduling auto-delete tasks
huey = RedisHuey("telegram-bot", url=REDIS_URL)

# Initialize AgenticHandler
agentic_handler = AgenticHandler(bot, gemini_client, mongo_store, huey)


def send_long_message(chat_id, text, reply_to_message_id=None, parse_mode=None):
    """Split and send long messages."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        bot.send_message(chat_id, text, reply_to_message_id=reply_to_message_id, parse_mode=parse_mode)
        return

    # Split by paragraphs first, then by length
    chunks = []
    current_chunk = ""

    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 <= MAX_MESSAGE_LENGTH:
            current_chunk += line + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(line) > MAX_MESSAGE_LENGTH:
                # Split long lines
                for i in range(0, len(line), MAX_MESSAGE_LENGTH):
                    chunks.append(line[i : i + MAX_MESSAGE_LENGTH])
                current_chunk = ""
            else:
                current_chunk = line + "\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    for i, chunk in enumerate(chunks):
        # Only reply to first message
        reply_id = reply_to_message_id if i == 0 else None
        bot.send_message(chat_id, chunk, reply_to_message_id=reply_id, parse_mode=parse_mode)


BOT_USERNAME = "@engeybot"


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all incoming messages."""
    user_id = message.from_user.id
    text = message.text or ""

    # Only respond to allowed users (required)
    if not ALLOWED_USERS or user_id not in ALLOWED_USERS:
        return

    if not text:
        return

    chat_id = message.chat.id
    message_id = message.message_id
    chat_type = message.chat.type

    print(f"Chat type: {chat_type}, User: {user_id}, Text: {text[:50]}...")

    # In groups, only respond when tagged
    if chat_type in ("group", "supergroup"):
        if BOT_USERNAME.lower() not in text.lower():
            print("Group message without mention, skipping")
            return
        # Remove the bot mention from text
        text = text.replace(BOT_USERNAME, "").replace(BOT_USERNAME.lower(), "").strip()

    try:
        # Route the message
        route = route_message(text)

        if route == RouteType.IGNORE:
            return

        # Send typing indicator
        bot.send_chat_action(chat_id, "typing")

        if route == RouteType.IMAGE:
            text_response, image_data = generate_image_response(text)
            if image_data:
                photo = io.BytesIO(image_data)
                photo.name = "diagram.png"
                bot.send_photo(
                    chat_id,
                    photo,
                    caption=text_response[:1024] if text_response else None,
                    reply_to_message_id=message_id,
                )
            elif text_response:
                send_long_message(chat_id, text_response, message_id)
        elif route == RouteType.AGENTIC:
            # Handle complex multi-faceted questions with agentic pipeline
            agentic_handler.handle(message)
        elif route == RouteType.GROUNDED:
            response, use_html = generate_grounded_response(text)
            if response:
                parse_mode = "HTML" if use_html else "Markdown"
                send_long_message(chat_id, response, message_id, parse_mode)
        elif route == RouteType.SIMPLE:
            response = generate_simple_response(text)
            if response:
                send_long_message(chat_id, response, message_id, "Markdown")

    except Exception as e:
        traceback.print_exc()
        sys.stdout.flush()


def main():
    """Start the bot."""
    import os

    if MODE == "PROD":
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK env variable is required in PROD mode")

        from flask import Flask, request

        app = Flask(__name__)

        @app.route(f"/{BOT_TOKEN}", methods=["POST"])
        def webhook():
            update = telebot.types.Update.de_json(request.get_json())
            bot.process_new_updates([update])
            return "OK", 200

        @app.route("/health", methods=["GET"])
        def health():
            return "OK", 200

        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        print(f"Bot starting in PROD mode with webhook: {WEBHOOK_URL}")

        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        print("Bot starting in DEV mode (polling)...")
        bot.infinity_polling()


if __name__ == "__main__":
    main()
