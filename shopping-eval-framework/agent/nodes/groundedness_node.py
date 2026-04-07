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
    spec_str = json.dumps(product.get("specs", {}), indent=2)
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
    return result


@traced_node("GroundednessNode")
def groundedness_node(state: dict) -> dict:
    products = state.get("ranked_products", [])
    constraints = state.get("parsed_constraints", [])
    annotations = []

    for product in products:
        annotation = check_product_groundedness(product, constraints)
        annotations.append(annotation)

    return {
        **state,
        "groundedness_annotations": annotations
    }
