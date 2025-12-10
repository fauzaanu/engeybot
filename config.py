"""Configuration and environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Whitelist of allowed user IDs (comma-separated in env)
ALLOWED_USERS: list[int] = []
if os.environ.get("ALLOWED_USERS"):
    ALLOWED_USERS = [int(u.strip()) for u in os.environ.get("ALLOWED_USERS").split(",")]

# Mode: DEV (polling) or PROD (webhook)
MODE = os.environ.get("MODE", "DEV").upper()
WEBHOOK_URL = os.environ.get("WEBHOOK")

SYSTEM_INSTRUCTION = """You are a helpful assistant in a Telegram group chat. Always respond in Dhivehi (ދިވެހި).
Provide detailed, informative responses."""
