"""Message routing using Gemini Flash."""

from enum import Enum
from pydantic import BaseModel, Field
from google import genai

from config import GEMINI_API_KEY

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
