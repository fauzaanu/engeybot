"""
Telegram bot with Gemini grounding and image generation capabilities.
- Uses Gemini Flash to route responses
- Can generate image diagrams with Nano Banana Pro
"""

import os
import io
from enum import Enum
import telebot
from telebot import formatting
from dotenv import load_dotenv
from pydantic import BaseModel, Field
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


class RouteType(str, Enum):
    IMAGE = "IMAGE"
    GROUNDED = "GROUNDED"
    SIMPLE = "SIMPLE"
    IGNORE = "IGNORE"


class MessageRoute(BaseModel):
    route: RouteType = Field(description="The type of response to generate")
    reason: str = Field(description="Brief reason for this routing decision")


def route_message(text: str) -> RouteType:
    """Use Gemini Flash with structured output to decide how to respond."""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""Analyze this message and decide the best response type:
- IMAGE: user wants a diagram, chart, visualization, or image
- GROUNDED: factual question needing current/accurate info (news, facts, dates, people, events)
- SIMPLE: casual chat, greeting, or doesn't need web search
- IGNORE: not a question or doesn't need a response

Message: {text}""",
        config={
            "response_mime_type": "application/json",
            "response_json_schema": MessageRoute.model_json_schema(),
        },
    )
    result = MessageRoute.model_validate_json(response.text)
    print(f"Route: {result.route} - {result.reason}")
    return result.route


SYSTEM_INSTRUCTION = """You are a helpful assistant in a Telegram group chat. Always respond in Dhivehi (ދިވެހި).
Provide detailed, informative responses."""


def generate_grounded_response(message: str) -> tuple[str, bool]:
    """Generate a response using Gemini with Google Search grounding."""
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        system_instruction=SYSTEM_INSTRUCTION + "\nAlways use Google Search to verify and ground your answers.",
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=message,
        config=config,
    )
    text = response.text.strip()

    # Add sources from grounding metadata
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


def generate_simple_response(message: str) -> str:
    """Generate a simple response without grounding."""
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=message,
        config=config,
    )
    return response.text.strip()


def generate_image_response(question: str) -> tuple[str, bytes | None]:
    """Generate an image diagram using Nano Banana Pro."""
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        tools=[types.Tool(google_search=types.GoogleSearch())],
        system_instruction="You create visual diagrams and explanations. Always respond in Dhivehi (ދިވެހި).",
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
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
                    reply_to_message_id=message_id
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
        print(f"Error: {e}")
        bot.reply_to(message, "Sorry, I encountered an error.")


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
        
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        print(f"Bot starting in PROD mode with webhook: {WEBHOOK_URL}")
        
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        print("Bot starting in DEV mode (polling)...")
        bot.infinity_polling()


if __name__ == "__main__":
    main()
