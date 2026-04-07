from langchain_google_genai import ChatGoogleGenerativeAI
import json
import os
import re
from dotenv import load_dotenv
from agent.tracing import traced_node
from agent.prompts import compile_to_messages

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


@traced_node("IntentNode")
def intent_node(state: dict) -> dict:
    history = state.get("conversation_history", [])
    query = state["query"]

    # Pre-compute user message — Langfuse templates don't support conditionals
    if history:
        history_str = "\n".join(
            f"{m['role']}: {m['content']}" for m in history
        )
        user_message = (
            f"Conversation so far:\n{history_str}\n\n"
            f"New message: {query}\n\n"
            f"Important: constraints accumulate across turns. Include all "
            f"constraints from earlier turns plus any new ones from this "
            f"message."
        )
    else:
        user_message = query

    messages, prompt_version = compile_to_messages(
        "intent-extraction", user_message=user_message
    )

    # Log prompt version to the current Langfuse span for attribution
    try:
        from langfuse import get_client
        get_client().update_current_span(metadata={
            "prompt_name": "intent-extraction",
            "prompt_version": prompt_version,
        })
    except Exception:
        pass

    response = llm.invoke(messages)
    parsed = _parse_json(response.content)

    return {
        **state,
        "parsed_constraints": parsed.get("constraints", []),
        "category": parsed.get("category"),
    }
