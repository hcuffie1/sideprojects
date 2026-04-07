"""
Langfuse-managed prompt registry for the shopping agent.

All LLM prompts are defined here as the canonical source of truth.
When LANGFUSE_PUBLIC_KEY is set, prompts are fetched from Langfuse by name
and label so that prompt versions are tracked against every trace.
When Langfuse is unavailable, a local fallback mimics the same .compile() API.

Usage in a node:
    from agent.prompts import compile_to_messages

    messages, prompt_version = compile_to_messages(
        "intent-extraction", user_message=user_message
    )
    # log prompt_version to the current Langfuse span for attribution

Bootstrap prompts in Langfuse once:
    python scripts/seed_prompts.py
"""
import os
from langchain_core.messages import SystemMessage, HumanMessage

# ─────────────────────────────────────────────────────────────────────────────
# Canonical prompt definitions
# Variables use {{double_braces}} — Langfuse native syntax.
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_DEFINITIONS: dict[str, dict] = {
    "intent-extraction": {
        "type": "chat",
        "prompt": [
            {
                "role": "system",
                "content": (
                    "You are a shopping assistant that extracts structured "
                    "intent from user queries. Extract:\n"
                    "1. product category (outdoor_furniture, kids_toys, "
                    "consumer_electronics, or unknown)\n"
                    "2. hard constraints (MUST be satisfied) — price limits, "
                    "size limits, capacity requirements\n"
                    "3. soft constraints (preferences) — color, brand, style\n\n"
                    "Return JSON only, no other text:\n"
                    "{\n"
                    '  "category": "string",\n'
                    '  "constraints": [\n'
                    '    {"field": "string", "op": "lte|gte|eq|contains", '
                    '"value": any, "is_hard": bool}\n'
                    "  ],\n"
                    '  "search_terms": ["string"]\n'
                    "}\n\n"
                    "Examples of field names: price, diameter_inches, weight_lbs, "
                    "max_umbrella_size_feet,\nage_range_min, battery_life_hours, "
                    "screen_size_inches"
                ),
            },
            {
                "role": "user",
                # Conditional history logic is pre-computed in intent_node.py
                # and passed as a single compiled user_message variable.
                "content": "{{user_message}}",
            },
        ],
    },
    "groundedness-check": {
        "type": "chat",
        "prompt": [
            {
                "role": "system",
                "content": (
                    "You are evaluating whether a product's specs support "
                    "specific claims about it. Given a product's spec data "
                    "and a potential claim, determine if the claim is grounded "
                    "in the actual spec data.\n\n"
                    "Return JSON only:\n"
                    "{\n"
                    '  "is_grounded": bool,\n'
                    '  "grounded_fields": ["field_name"],\n'
                    '  "ungrounded_claims": ["claim text"],\n'
                    '  "score": 0.0\n'
                    "}\n\n"
                    "scoring rules:\n"
                    "- score 1.0 = every constraint can be directly verified "
                    "from spec fields\n"
                    "- score 0.0 = no constraints can be verified (specs are "
                    "missing or irrelevant)\n"
                    "- score 0.5 = some constraints verifiable, some not\n"
                    "- If a required spec field is completely absent, that "
                    "constraint is NOT grounded"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Product specs:\n{{specs}}\n\n"
                    "User constraints that this product should satisfy:\n"
                    "{{constraints}}\n\n"
                    "Can the product specs actually verify these constraints "
                    "are met?\nAre there any claims that would need to be made "
                    "about this product\nthat aren't supported by the spec data?"
                ),
            },
        ],
    },
    "response-generation": {
        "type": "chat",
        "prompt": [
            {
                "role": "system",
                "content": (
                    "You are a shopping assistant. Generate a helpful response\n"
                    "recommending products to the user.\n\n"
                    "RULES:\n"
                    "1. Only recommend products that are in stock\n"
                    "2. Only make claims supported by actual product specs — "
                    "never infer capabilities\n"
                    '3. If a spec field is missing, say "spec not listed" '
                    "rather than guessing\n"
                    "4. Be direct about what you know and don't know\n"
                    "5. Never claim a product can do something if the spec "
                    "doesn't say so"
                ),
            },
            {
                "role": "user",
                "content": (
                    "User query: {{query}}\n\n"
                    "Products I can recommend (all in stock, specs verified):\n"
                    "{{products}}\n\n"
                    "Write a helpful recommendation. For each product, only "
                    "cite spec values\nthat are explicitly listed in the specs "
                    "object."
                ),
            },
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Local fallback — mimics langfuse prompt .compile() API
# ─────────────────────────────────────────────────────────────────────────────

class _LocalPrompt:
    """
    Used when Langfuse is unavailable (no LANGFUSE_PUBLIC_KEY).
    Provides the same .compile(**kwargs) interface as a real Langfuse prompt.
    """

    def __init__(self, name: str):
        self.name = name
        self.version = "local"
        self._defn = PROMPT_DEFINITIONS[name]

    def compile(self, **kwargs) -> list[dict]:
        messages = []
        for msg in self._defn["prompt"]:
            content = msg["content"]
            for k, v in kwargs.items():
                content = content.replace(f"{{{{{k}}}}}", str(v))
            messages.append({"role": msg["role"], "content": content})
        return messages


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_prompt(name: str):
    """
    Fetch prompt from Langfuse (label='production') or fall back to local def.
    Returns an object with .compile(**kwargs) -> list[dict] and .version attr.
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return _LocalPrompt(name)
    try:
        from langfuse import get_client
        prompt_type = PROMPT_DEFINITIONS[name]["type"]
        return get_client().get_prompt(name, label="production", type=prompt_type)
    except Exception:
        return _LocalPrompt(name)


def compile_to_messages(
    name: str, **kwargs
) -> tuple[list[SystemMessage | HumanMessage], str]:
    """
    Fetch prompt, compile with variables, and convert to LangChain messages.

    Returns:
        messages: list of SystemMessage / HumanMessage ready for llm.invoke()
        prompt_version: version string for Langfuse span metadata attribution
    """
    prompt = get_prompt(name)
    compiled = prompt.compile(**kwargs)

    messages = []
    for msg in compiled:
        if msg["role"] == "system":
            messages.append(SystemMessage(content=msg["content"]))
        else:
            messages.append(HumanMessage(content=msg["content"]))

    return messages, str(getattr(prompt, "version", "local"))
