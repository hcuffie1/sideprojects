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

    # Prepend user memory context if a user_id is in state
    user_id = state.get("user_id")
    if user_id:
        try:
            from agent.memory import MemoryManager
            ctx = MemoryManager().get_user_context(user_id)
            if ctx:
                prefs = ", ".join(
                    f"{k}={v['value']} ({v['memory_type']})"
                    for k, v in ctx.get("preferences", {}).items()
                )
                avoid = ", ".join(ctx.get("avoid_ids", []))
                memory_block = (
                    f"[User context for {ctx.get('name', user_id)}]\n"
                    f"Preferences: {prefs or 'none'}\n"
                    f"Do not recommend product IDs: {avoid or 'none'}\n\n"
                )
                user_message = memory_block + user_message
        except Exception:
            pass  # memory unavailable — degrade gracefully

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

    # Accumulate token usage
    usage = getattr(response, "usage_metadata", None) or {}
    prior = state.get("_token_usage") or {"input_total": 0, "output_total": 0}
    token_usage = {
        "input_total": prior["input_total"] + (usage.get("input_tokens") or 0),
        "output_total": prior["output_total"] + (usage.get("output_tokens") or 0),
    }

    return {
        **state,
        "parsed_constraints": parsed.get("constraints", []),
        "category": parsed.get("category"),
        "_token_usage": token_usage,
    }
