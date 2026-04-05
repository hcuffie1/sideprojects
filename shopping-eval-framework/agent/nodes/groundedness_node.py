from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import os
import re
from dotenv import load_dotenv

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


GROUNDEDNESS_PROMPT = """You are evaluating whether a product's specs support
specific claims about it. Given a product's spec data and a potential claim,
determine if the claim is grounded in the actual spec data.

Return JSON only:
{
  "is_grounded": bool,
  "grounded_fields": ["field_name"],
  "ungrounded_claims": ["claim text"],
  "score": 0.0
}

scoring rules:
- score 1.0 = every constraint can be directly verified from spec fields
- score 0.0 = no constraints can be verified (specs are missing or irrelevant)
- score 0.5 = some constraints verifiable, some not
- If a required spec field is completely absent, that constraint is NOT
  grounded"""


def check_product_groundedness(product: dict, constraints: list) -> dict:
    """Check if specs can support the constraints user asked for."""
    spec_str = json.dumps(product.get("specs", {}), indent=2)
    constraint_str = json.dumps(constraints, indent=2)

    prompt = f"""Product specs:
{spec_str}

User constraints that this product should satisfy:
{constraint_str}

Can the product specs actually verify these constraints are met?
Are there any claims that would need to be made about this product
that aren't supported by the spec data?"""

    messages = [
        SystemMessage(content=GROUNDEDNESS_PROMPT),
        HumanMessage(content=prompt)
    ]
    response = llm.invoke(messages)
    result = _parse_json(response.content)
    result["product_id"] = product["id"]
    return result


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
