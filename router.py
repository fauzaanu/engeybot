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
    AGENTIC = "AGENTIC"  # Complex multi-faceted questions requiring research
    IGNORE = "IGNORE"


class MessageRoute(BaseModel):
    route: RouteType = Field(description="The type of response to generate")
    reason: str = Field(description="Brief reason for this routing decision")


def route_message(text: str) -> RouteType:
    """Use Gemini Flash with structured output to decide how to respond."""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""Analyze this message and decide the best response type:
- IMAGE: user wants a diagram, chart, visualization, or image created
- AGENTIC: ANY question or request that needs information or research - this is the DEFAULT for questions
- SIMPLE: ONLY for casual chat like greetings ("hi", "hello"), thanks ("thank you"), or very basic conversation
- IGNORE: ONLY use for completely empty or meaningless input

IMPORTANT: Route ALL questions to AGENTIC. This includes:
- Factual questions
- Opinion questions  
- Comparisons
- Explanations
- Any request for information

Only use SIMPLE for pure greetings/thanks with no actual question.
Any question in any language should go to AGENTIC.

Message: {text}""",
        config={
            "response_mime_type": "application/json",
            "response_json_schema": MessageRoute.model_json_schema(),
        },
    )
    result = MessageRoute.model_validate_json(response.text)
    print(f"Route: {result.route} - {result.reason}", flush=True)
    return result.route
