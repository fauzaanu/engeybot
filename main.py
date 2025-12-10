"""
Telegram bot with Gemini grounding and image generation capabilities.
- Only responds to ?? questions from allowed users
- Can generate image diagrams with Nano Banana Pro
"""

import os
import io
import telebot
from telebot import formatting
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize clients
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Whitelist of allowed user IDs (comma-separated in env)
ALLOWED_USERS: list[int] = []
if os.environ.get("ALLOWED_USERS"):
    ALLOWED_USERS = [int(u.strip()) for u in os.environ.get("ALLOWED_USERS").split(",")]

# Mode: DEV (polling) or PROD (webhook)
MODE = os.environ.get("MODE", "DEV").upper()
WEBHOOK_URL = os.environ.get("WEBHOOK")

bot = telebot.TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)


def should_generate_image(text: str) -> bool:
    """Check if the question asks for a diagram/image."""
    image_keywords = [
        "diagram", "image", "picture", "draw", "visualize", "visualization",
        "chart", "graph", "illustration", "sketch", "infographic", "flowchart",
        "show me", "create a visual", "generate an image"
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in image_keywords)


SYSTEM_INSTRUCTION = """You are a helpful assistant in a Telegram group chat. Always respond in Dhivehi (ދިވެހި).
Always use Google Search to verify and ground your answers with current information.
Provide detailed, informative responses."""


def generate_grounded_response(message: str) -> tuple[str | None, bool]:
    """Generate a response using Gemini with Google Search grounding."""
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        system_instruction=SYSTEM_INSTRUCTION,
    )

    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=message,
        config=config,
    )
    text = response.text.strip()

    # Add sources from grounding metadata (titles only) as collapsed quote
    sources = set()
    try:
        if response.candidates and response.candidates[0].grounding_metadata:
            metadata = response.candidates[0].grounding_metadata
            chunks = getattr(metadata, 'grounding_chunks', None) or []
            for chunk in chunks[:5]:
                if hasattr(chunk, 'web') and chunk.web:
                    title = getattr(chunk.web, 'title', None)
                    if title:
                        sources.add(title)
    except Exception as e:
        print(f"Error extracting sources: {e}")
    
    if sources:
        sources_text = "މަސްދަރުތައް: " + ", ".join(sources)
        text += "\n\n" + formatting.hcite(sources_text, escape=False, expandable=False)
        return text, True
    
    return text, False


def generate_image_response(question: str) -> tuple[str, bytes | None]:
    """Generate an image diagram using Nano Banana Pro."""
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        tools=[types.Tool(google_search=types.GoogleSearch())],
        system_instruction="You create visual diagrams and explanations. Always respond in Dhivehi (ދިވެހި).",
    )

    response = client.models.generate_content(
        model="gemini-3-pro-image-preview",
        contents=question,
        config=config,
    )
    
    text_response = ""
    image_data = None
    
    for part in response.parts:
        if part.text is not None:
            text_response = part.text
        elif part.inline_data is not None:
            image_data = part.inline_data.data
    
    return text_response, image_data


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all incoming messages."""
    # Only respond to allowed users (required)
    user_id = message.from_user.id
    if not ALLOWED_USERS or user_id not in ALLOWED_USERS:
        return
    
    text = message.text or ""
    if not text:
        return
    
    # Only respond to messages containing ??
    if "??" not in text:
        return
    
    # Remove ?? from the text for processing
    text = text.replace("??", "").strip()
    
    chat_id = message.chat.id
    message_id = message.message_id
    
    try:
        # Send typing indicator
        bot.send_chat_action(chat_id, "typing")
        
        if should_generate_image(text):
            # Generate image diagram
            text_response, image_data = generate_image_response(text)
            
            if image_data:
                photo = io.BytesIO(image_data)
                photo.name = "diagram.png"
                bot.send_photo(
                    chat_id,
                    photo,
                    caption=text_response[:1024] if text_response else None,
                    reply_to_message_id=message_id
                )
            elif text_response:
                bot.reply_to(message, text_response)
            else:
                bot.reply_to(message, "Sorry, I couldn't generate an image for that request.")
        else:
            # Generate grounded text response
            response, use_html = generate_grounded_response(text)
            if response:
                bot.reply_to(message, response, parse_mode="HTML" if use_html else None)
            
    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "Sorry, I encountered an error processing your question.")


def main():
    """Start the bot."""
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
        
        # Set webhook
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        print(f"Bot starting in PROD mode with webhook: {WEBHOOK_URL}")
        
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        print("Bot starting in DEV mode (polling)...")
        bot.infinity_polling()


if __name__ == "__main__":
    main()
