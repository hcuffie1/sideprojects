import pytest
from dotenv import load_dotenv

load_dotenv()


def make_state(ranked_products, annotations, query="test query"):
    return {
        "query": query,
        "conversation_history": [],
        "parsed_constraints": [],
        "category": "outdoor_furniture",
        "candidate_products": [],
        "filtered_products": [],
        "constraint_violations": [],
        "ranked_products": ranked_products,
        "groundedness_annotations": annotations,
        "final_response": "",
        "agent_rationale": "",
        "trace_id": None,
        "eval_scores": None
    }


def test_no_grounded_products_returns_safe_response():
    """When no products pass groundedness, agent should say so — not fabricate"""
    from agent.nodes.response_node import response_node

    ranked = [{"id": "prod_bad", "name": "Bad Product", "in_stock": True, "specs": {}}]
    annotations = [{"product_id": "prod_bad", "score": 0.1, "is_grounded": False,
                    "grounded_fields": [], "ungrounded_claims": ["all claims"]}]

    state = make_state(ranked, annotations)
    result = response_node(state)

    assert result["final_response"]
    assert "wasn't able" in result["final_response"].lower() or \
           "couldn't" in result["final_response"].lower() or \
           "don't" in result["final_response"].lower() or \
           "cannot" in result["final_response"].lower() or \
           "not find" in result["final_response"].lower()
    assert result["agent_rationale"] == "No products passed groundedness check"


def test_grounded_products_generate_response():
    """Products that pass groundedness should appear in the response"""
    from agent.nodes.response_node import response_node

    ranked = [{
        "id": "prod_good",
        "name": "Grand Umbrella Base",
        "in_stock": True,
        "specs": {
            "weight_lbs": 75,
            "diameter_inches": 20,
            "max_umbrella_size_feet": 15,
            "material": "cast iron"
        }
    }]
    annotations = [{"product_id": "prod_good", "score": 0.9, "is_grounded": True,
                    "grounded_fields": ["max_umbrella_size_feet"], "ungrounded_claims": []}]

    state = make_state(ranked, annotations, query="umbrella base for 15 foot umbrella")
    result = response_node(state)

    assert result["final_response"]
    assert len(result["final_response"]) > 50  # actual content, not empty
    assert "Grand Umbrella Base" in result["final_response"]
