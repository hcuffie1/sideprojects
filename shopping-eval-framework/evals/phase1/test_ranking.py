import pytest
from agent.nodes.ranking_node import ranking_node, score_product

PRODUCTS = [
    {
        "id": "prod_rich_specs",
        "name": "Well Specified Product",
        "in_stock": True,
        "specs": {
            "weight_lbs": 50,
            "diameter_inches": 20,
            "max_umbrella_size_feet": 15,
            "material": "cast iron",
            "weather_resistant": True,
            "color": "black",
            "has_wheels": False,
            "pole_diameter_inches": 1.5
        }
    },
    {
        "id": "prod_sparse_specs",
        "name": "Barely Specified Product",
        "in_stock": True,
        "specs": {
            "weight_lbs": 40
        }
    },
    {
        "id": "prod_no_specs",
        "name": "No Spec Product",
        "in_stock": True,
        "specs": {}
    }
]


def make_state(products, constraints=None):
    return {
        "query": "test",
        "conversation_history": [],
        "parsed_constraints": constraints or [],
        "category": "outdoor_furniture",
        "candidate_products": products,
        "filtered_products": products,
        "constraint_violations": [],
        "ranked_products": [],
        "groundedness_annotations": [],
        "final_response": "",
        "agent_rationale": "",
        "trace_id": None,
        "eval_scores": None
    }


def test_ranks_by_spec_completeness():
    state = make_state(PRODUCTS)
    result = ranking_node(state)
    ranked_ids = [p["id"] for p in result["ranked_products"]]
    # richest specs should come first
    assert ranked_ids[0] == "prod_rich_specs"


def test_caps_at_5_results():
    many_products = [
        {"id": f"prod_{i}", "name": f"Product {i}", "in_stock": True, "specs": {"weight_lbs": i}}
        for i in range(10)
    ]
    state = make_state(many_products)
    result = ranking_node(state)
    assert len(result["ranked_products"]) <= 5


def test_soft_constraint_bonus():
    state = make_state(
        [PRODUCTS[0], PRODUCTS[1]],
        constraints=[{"field": "color", "op": "eq", "value": "black", "is_hard": False}]
    )
    score_rich = score_product(PRODUCTS[0], state)
    score_sparse = score_product(PRODUCTS[1], state)
    # rich specs product has color field, gets bonus
    assert score_rich > score_sparse


def test_empty_input_returns_empty():
    state = make_state([])
    result = ranking_node(state)
    assert result["ranked_products"] == []
