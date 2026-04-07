from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import os
import re
from dotenv import load_dotenv
from agent.tracing import traced_node

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.environ["GEMINI_API_KEY"]
)


def _parse_json(text: str) -> dict:
    """Strip markdown code fences Gemini sometimes adds, then parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


INTENT_SYSTEM_PROMPT = """You are a shopping assistant that extracts structured
intent from user queries. Extract:
1. product category (outdoor_furniture, kids_toys, consumer_electronics, or unknown)
2. hard constraints (MUST be satisfied) — price limits, size limits, capacity requirements
3. soft constraints (preferences) — color, brand, style

Return JSON only, no other text:
{
  "category": "string",
  "constraints": [
    {"field": "string", "op": "lte|gte|eq|contains", "value": any, "is_hard": bool}
  ],
  "search_terms": ["string"]
}

Examples of field names: price, diameter_inches, weight_lbs, max_umbrella_size_feet,
age_range_min, battery_life_hours, screen_size_inches"""


@traced_node("IntentNode")
def intent_node(state: dict) -> dict:
    history = state.get("conversation_history", [])
    query = state["query"]

    if history:
        history_str = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        query = (
            f"Conversation so far:\n{history_str}\n\n"
            f"New message: {query}\n\n"
            f"Important: constraints accumulate across turns. Include all constraints "
            f"from earlier turns plus any new ones from this message."
        )

    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=query)
    ]
    response = llm.invoke(messages)
    parsed = _parse_json(response.content)

    return {
        **state,
        "parsed_constraints": parsed.get("constraints", []),
        "category": parsed.get("category"),
    }
