from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.environ["GEMINI_API_KEY"]
)

RESPONSE_SYSTEM = """You are a shopping assistant. Generate a helpful response
recommending products to the user.

RULES:
1. Only recommend products that are in stock
2. Only make claims supported by actual product specs — never infer capabilities
3. If a spec field is missing, say "spec not listed" rather than guessing
4. Be direct about what you know and don't know
5. Never claim a product can do something if the spec doesn't say so"""


def response_node(state: dict) -> dict:
    ranked = state.get("ranked_products", [])
    annotations = state.get("groundedness_annotations", [])
    query = state.get("query", "")

    # Filter to only grounded products (score > 0.5)
    grounded_ids = {a["product_id"] for a in annotations if a.get("score", 0) > 0.5}
    trustworthy = [p for p in ranked if p["id"] in grounded_ids]

    if not trustworthy:
        return {
            **state,
            "final_response": "I wasn't able to find products I can confidently recommend for your specific requirements. The products I found either don't meet your constraints or I couldn't verify their specs.",
            "agent_rationale": "No products passed groundedness check"
        }

    products_str = json.dumps(trustworthy[:3], indent=2)
    prompt = f"""User query: {query}

Products I can recommend (all in stock, specs verified):
{products_str}

Write a helpful recommendation. For each product, only cite spec values
that are explicitly listed in the specs object."""

    messages = [
        SystemMessage(content=RESPONSE_SYSTEM),
        HumanMessage(content=prompt)
    ]
    response = llm.invoke(messages)

    return {
        **state,
        "final_response": response.content,
        "agent_rationale": f"Recommended {len(trustworthy)} grounded products from {len(ranked)} ranked results"
    }
