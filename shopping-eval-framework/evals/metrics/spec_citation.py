"""
Spec citation accuracy — detects when final_response cites a wrong value.

Groundedness (in groundedness_node.py) checks whether specs EXIST to back
a constraint. This module checks whether the values the agent STATED in its
final_response match the actual spec values of the recommended product.

Catches errors like:
  - Agent says "30-hour battery" when spec says battery_life_hours: 25
  - Agent says "this is not educational" when spec says educational: True
  - Agent says "fits a 13-foot umbrella" when spec says max_umbrella_size_feet: 11

Usage:
    from evals.metrics.spec_citation import citation_accuracy
    result = citation_accuracy(agent_result)
    # result["score"] is 0.0–1.0 (None if no ranked products)
"""
import json
import os
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.environ["GEMINI_API_KEY"],
)

_SYSTEM_PROMPT = (
    "You are checking whether a product recommendation accurately cites spec values.\n"
    "Given the product's actual specs and a recommendation text, extract every specific "
    "claim the text makes about the product — numbers, measurements, model names, AND "
    "boolean properties (e.g., 'is educational', 'is waterproof', 'supports fast charging').\n\n"
    "For each claim:\n"
    "- Match it to the closest spec field by name or meaning\n"
    "- Compare the cited value against the actual spec value\n"
    "- For boolean fields: 'This toy is educational' vs educational:true → accurate. "
    "'This toy is not educational' vs educational:true → inaccurate.\n"
    "- For numeric fields: cited value must equal actual value to be accurate\n\n"
    "Return JSON only, no other text:\n"
    "{\n"
    '  "claims": [\n'
    '    {"field": "battery_life_hours", "cited_value": 30, "actual_value": 25, "accurate": false}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Only extract verifiable factual claims (numbers, booleans, model names)\n"
    "- Skip soft claims ('a great choice', 'highly recommended', 'perfect for')\n"
    "- Skip claims where no matching spec field exists\n"
    "- If no verifiable claims are made, return {\"claims\": []}"
)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def citation_accuracy(result: dict) -> dict:
    """
    Check whether final_response accurately cites spec values for the
    top-ranked product.

    Returns:
        {
          "score": float | None,  # None if no ranked products or no response
          "claims": list[dict],   # all extracted claims with accurate flag
          "product_id": str | None,
        }
    """
    ranked = result.get("ranked_products", [])
    response_text = result.get("final_response", "")

    if not ranked or not response_text:
        return {"score": None, "claims": [], "product_id": None}

    top = ranked[0]
    specs = top.get("specs", {})
    product_id = top.get("id")

    user_message = (
        f"Product specs:\n{json.dumps(specs, indent=2)}\n\n"
        f"Recommendation text:\n{response_text}"
    )

    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    try:
        response = _llm.invoke(messages)
        parsed = _parse_json(response.content)
    except Exception:
        return {"score": None, "claims": [], "product_id": product_id}

    claims = parsed.get("claims", [])
    if not claims:
        # No verifiable claims made → agent was appropriately hedged
        return {"score": 1.0, "claims": [], "product_id": product_id}

    accurate_count = sum(1 for c in claims if c.get("accurate"))
    score = accurate_count / len(claims)

    return {
        "score": score,
        "claims": claims,
        "product_id": product_id,
    }
