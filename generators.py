"""Response generators using Gemini."""

from telebot import formatting
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, SYSTEM_INSTRUCTION

client = genai.Client(api_key=GEMINI_API_KEY)


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
            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks[:5]:
                if hasattr(chunk, "web") and chunk.web:
                    title = getattr(chunk.web, "title", None)
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
