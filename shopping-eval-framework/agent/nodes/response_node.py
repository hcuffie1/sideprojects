from langchain_google_genai import ChatGoogleGenerativeAI
import json
import os
from dotenv import load_dotenv
from agent.tracing import traced_node
from agent.prompts import compile_to_messages

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.environ["GEMINI_API_KEY"]
)


@traced_node("ResponseNode")
def response_node(state: dict) -> dict:
    ranked = state.get("ranked_products", [])
    annotations = state.get("groundedness_annotations", [])
    query = state.get("query", "")

    # Filter to only grounded products (score > 0.5)
    grounded_ids = {
        a["product_id"] for a in annotations if a.get("score", 0) > 0.5
    }
    trustworthy = [p for p in ranked if p["id"] in grounded_ids]

    if not trustworthy:
        final_response = (
            "I wasn't able to find products I can confidently recommend "
            "for your specific requirements. The products I found either "
            "don't meet your constraints or I couldn't verify their specs."
        )
        updated_history = state.get("conversation_history", []) + [
            {"role": "user", "content": state.get("query", "")},
            {"role": "assistant", "content": final_response}
        ]
        return {
            **state,
            "final_response": final_response,
            "conversation_history": updated_history,
            "agent_rationale": "No products passed groundedness check"
        }

    products_str = json.dumps(trustworthy[:3], indent=2)
    messages, prompt_version = compile_to_messages(
        "response-generation", query=query, products=products_str
    )

    # Log prompt version to the current Langfuse span for attribution
    try:
        from langfuse import get_client
        get_client().update_current_span(metadata={
            "prompt_name": "response-generation",
            "prompt_version": prompt_version,
        })
    except Exception:
        pass

    response = llm.invoke(messages)

    updated_history = state.get("conversation_history", []) + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": response.content}
    ]
    return {
        **state,
        "final_response": response.content,
        "conversation_history": updated_history,
        "agent_rationale": (
            f"Recommended {len(trustworthy)} grounded products "
            f"from {len(ranked)} ranked results"
        )
    }
