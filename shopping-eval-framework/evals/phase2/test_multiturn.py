"""
Phase 2 multi-turn context retention tests.

Verifies that:
1. Category detected in turn 1 is retained in turn 2
2. Constraints accumulate across turns (not reset each turn)

These tests make real LLM calls. Run with:
    pytest evals/phase2/test_multiturn.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dotenv import load_dotenv

load_dotenv()

from agent.graph import agent

EMPTY_STATE = {
    "conversation_history": [],
    "query": "",
    "parsed_constraints": [],
    "category": None,
    "candidate_products": [],
    "filtered_products": [],
    "constraint_violations": [],
    "ranked_products": [],
    "groundedness_annotations": [],
    "final_response": "",
    "agent_rationale": "",
    "trace_id": None,
    "eval_scores": None,
}


def test_category_retained_across_turns():
    """
    Turn 1 establishes category=outdoor_furniture.
    Turn 2 adds a price constraint.
    Category should still be outdoor_furniture after turn 2.
    """
    state = {**EMPTY_STATE, "query": "I want an umbrella base"}
    state = agent.invoke(state)
    assert state["category"] == "outdoor_furniture", (
        f"Turn 1 category wrong: {state['category']}"
    )

    state["query"] = "make it under $200"
    state = agent.invoke(state)

    assert state["category"] == "outdoor_furniture", (
        f"Category changed after turn 2: {state['category']}"
    )
    price_constraints = [
        c for c in state.get("parsed_constraints", [])
        if c.get("field") == "price"
    ]
    assert price_constraints, (
        "Turn 2 price constraint not extracted from history"
    )
    assert any(c.get("value") == 200 for c in price_constraints), (
        f"Price constraint value wrong: {price_constraints}"
    )


def test_constraints_accumulate_across_turns():
    """
    q_007 multi-turn: umbrella base → 15ft capacity → under 24 inches wide.
    By turn 3, both capacity AND size constraints must be in parsed_constraints.
    """
    state = {**EMPTY_STATE, "query": "I'm looking for an umbrella base"}
    state = agent.invoke(state)

    state["query"] = "it needs to hold a 15 foot umbrella"
    state = agent.invoke(state)

    state["query"] = "and it has to be under 24 inches wide"
    state = agent.invoke(state)

    constraints = state.get("parsed_constraints", [])
    fields = {c.get("field") for c in constraints}

    assert "max_umbrella_size_feet" in fields, (
        f"Umbrella capacity constraint missing after 3 turns. Fields: {fields}"
    )
    assert "diameter_inches" in fields, (
        f"Diameter constraint missing after 3 turns. Fields: {fields}"
    )


def test_multi_turn_products_still_in_stock():
    """
    After multi-turn refinement, ranked products should all be in stock.
    """
    state = {**EMPTY_STATE, "query": "show me wireless headphones"}
    state = agent.invoke(state)

    state["query"] = "actually I need at least 30 hours battery life"
    state = agent.invoke(state)

    for p in state.get("ranked_products", []):
        assert p.get("in_stock"), (
            f"Out-of-stock product in multi-turn results: {p.get('id')}"
        )
