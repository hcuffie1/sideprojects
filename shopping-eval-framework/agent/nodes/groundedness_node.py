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


def check_product_groundedness(product: dict, constraints: list) -> dict:
    """Check if specs can support the constraints user asked for."""
    # Merge top-level product fields (price, name, category, etc.) with nested
    # specs so the LLM can verify constraints like "price lte 300" that live
    # on the product root, not inside specs.
    product_data = {k: v for k, v in product.items() if k not in ("specs", "id")}
    product_data.update(product.get("specs", {}))
    spec_str = json.dumps(product_data, indent=2)
    constraint_str = json.dumps(constraints, indent=2)

    messages, prompt_version = compile_to_messages(
        "groundedness-check", specs=spec_str, constraints=constraint_str
    )

    # Log prompt version to the current Langfuse span for attribution
    try:
        from langfuse import get_client
        get_client().update_current_span(metadata={
            "prompt_name": "groundedness-check",
            "prompt_version": prompt_version,
        })
    except Exception:
        pass

    response = llm.invoke(messages)
    result = _parse_json(response.content)
    result["product_id"] = product["id"]
    # Return raw usage for aggregation by the node
    usage = getattr(response, "usage_metadata", None) or {}
    result["_usage"] = {
        "input_tokens": usage.get("input_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
    }
    return result


@traced_node("GroundednessNode")
def groundedness_node(state: dict) -> dict:
    products = state.get("ranked_products", [])
    constraints = state.get("parsed_constraints", [])
    annotations = []
    input_tokens = 0
    output_tokens = 0

    for product in products:
        annotation = check_product_groundedness(product, constraints)
        node_usage = annotation.pop("_usage", {})
        input_tokens += node_usage.get("input_tokens", 0)
        output_tokens += node_usage.get("output_tokens", 0)
        annotations.append(annotation)

    prior = state.get("_token_usage") or {"input_total": 0, "output_total": 0}
    token_usage = {
        "input_total": prior["input_total"] + input_tokens,
        "output_total": prior["output_total"] + output_tokens,
    }

    return {
        **state,
        "groundedness_annotations": annotations,
        "_token_usage": token_usage,
    }
