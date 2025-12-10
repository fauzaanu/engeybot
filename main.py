"""Telegram bot with Gemini grounding and image generation."""

import io
import sys
import traceback
import telebot

from config import BOT_TOKEN, ALLOWED_USERS, MODE, WEBHOOK_URL
from router import route_message, RouteType
from generators import generate_grounded_response, generate_simple_response, generate_image_response

bot = telebot.TeleBot(BOT_TOKEN)


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
                bot.reply_to(message, text_response)
        elif route == RouteType.GROUNDED:
            response, use_html = generate_grounded_response(text)
            if response:
                parse_mode = "HTML" if use_html else "Markdown"
                bot.reply_to(message, response, parse_mode=parse_mode)
        elif route == RouteType.SIMPLE:
            response = generate_simple_response(text)
            if response:
                bot.reply_to(message, response, parse_mode="Markdown")

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
