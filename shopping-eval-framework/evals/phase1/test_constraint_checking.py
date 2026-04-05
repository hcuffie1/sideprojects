import pytest
from agent.nodes.constraint_check_node import constraint_check_node

SAMPLE_PRODUCTS = [
    {
        "id": "prod_good",
        "name": "Good Base",
        "in_stock": True,
        "specs": {"diameter_inches": 20, "max_umbrella_size_feet": 15, "weight_lbs": 50}
    },
    {
        "id": "prod_too_wide",
        "name": "Too Wide Base",
        "in_stock": True,
        "specs": {"diameter_inches": 28, "max_umbrella_size_feet": 15, "weight_lbs": 60}
    },
    {
        "id": "prod_missing_spec",
        "name": "Missing Spec Base",
        "in_stock": True,
        "specs": {"weight_lbs": 40}  # no diameter or umbrella size
    }
]


def make_state(products, constraints):
    return {
        "query": "test",
        "conversation_history": [],
        "parsed_constraints": constraints,
        "category": "outdoor_furniture",
        "candidate_products": products,
        "filtered_products": [],
        "constraint_violations": [],
        "ranked_products": [],
        "groundedness_annotations": [],
        "final_response": "",
        "agent_rationale": "",
        "trace_id": None,
        "eval_scores": None
    }


def test_filters_products_violating_hard_constraint():
    constraints = [{"field": "diameter_inches", "op": "lte", "value": 24, "is_hard": True}]
    state = make_state(SAMPLE_PRODUCTS, constraints)
    result = constraint_check_node(state)
    product_ids = [p["id"] for p in result["filtered_products"]]
    assert "prod_good" in product_ids
    assert "prod_too_wide" not in product_ids


def test_flags_missing_spec_as_violation():
    """Missing required spec should be treated as a constraint violation"""
    constraints = [{"field": "max_umbrella_size_feet", "op": "gte", "value": 15, "is_hard": True}]
    state = make_state([SAMPLE_PRODUCTS[2]], constraints)  # only missing spec product
    result = constraint_check_node(state)
    assert len(result["filtered_products"]) == 0
    assert len(result["constraint_violations"]) > 0
    assert result["constraint_violations"][0]["reason"] == "spec_missing"


def test_passes_product_satisfying_all_constraints():
    constraints = [
        {"field": "diameter_inches", "op": "lte", "value": 24, "is_hard": True},
        {"field": "max_umbrella_size_feet", "op": "gte", "value": 15, "is_hard": True}
    ]
    state = make_state([SAMPLE_PRODUCTS[0]], constraints)
    result = constraint_check_node(state)
    assert len(result["filtered_products"]) == 1
    assert result["filtered_products"][0]["id"] == "prod_good"


def test_soft_constraint_missing_spec_is_ok():
    """Missing spec for a soft constraint should NOT exclude the product"""
    constraints = [{"field": "color", "op": "eq", "value": "black", "is_hard": False}]
    state = make_state([SAMPLE_PRODUCTS[0]], constraints)
    result = constraint_check_node(state)
    assert len(result["filtered_products"]) == 1


def test_almost_satisfies_constraint_is_excluded():
    """Product with diameter 25 when limit is 24 must be excluded"""
    almost_product = {
        "id": "prod_almost",
        "name": "Almost Base",
        "in_stock": True,
        "specs": {"diameter_inches": 25, "max_umbrella_size_feet": 13}
    }
    constraints = [{"field": "diameter_inches", "op": "lte", "value": 24, "is_hard": True}]
    state = make_state([almost_product], constraints)
    result = constraint_check_node(state)
    assert len(result["filtered_products"]) == 0
    assert result["constraint_violations"][0]["actual"] == 25
