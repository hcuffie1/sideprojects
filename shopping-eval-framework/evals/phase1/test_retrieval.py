import pytest
from agent.nodes.retrieval_node import retrieval_node, load_catalog


def make_state(category: str) -> dict:
    return {
        "query": "test",
        "conversation_history": [],
        "parsed_constraints": [],
        "category": category,
        "candidate_products": [],
        "filtered_products": [],
        "constraint_violations": [],
        "ranked_products": [],
        "groundedness_annotations": [],
        "final_response": "",
        "agent_rationale": "",
        "trace_id": None,
        "eval_scores": None
    }


def test_loads_outdoor_furniture_catalog():
    products = load_catalog("outdoor_furniture")
    assert len(products) == 15


def test_loads_kids_toys_catalog():
    products = load_catalog("kids_toys")
    assert len(products) == 15


def test_loads_consumer_electronics_catalog():
    products = load_catalog("consumer_electronics")
    assert len(products) == 15


def test_returns_empty_for_unknown_category():
    products = load_catalog("nonexistent_category")
    assert products == []


def test_retrieval_filters_out_of_stock():
    state = make_state("outdoor_furniture")
    result = retrieval_node(state)
    for product in result["candidate_products"]:
        assert product.get("in_stock") is True, (
            f"Out-of-stock product {product['id']} was returned by retrieval"
        )


def test_retrieval_returns_candidates():
    state = make_state("consumer_electronics")
    result = retrieval_node(state)
    assert len(result["candidate_products"]) > 0


def test_retrieval_caps_at_20():
    state = make_state("outdoor_furniture")
    result = retrieval_node(state)
    assert len(result["candidate_products"]) <= 20
