import pytest
from dotenv import load_dotenv

load_dotenv()


def make_state(query: str) -> dict:
    return {
        "query": query,
        "conversation_history": [],
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
        "eval_scores": None
    }


def test_extracts_size_constraint():
    from agent.nodes.intent_node import intent_node
    state = make_state("umbrella base less than 24 inches wide")
    result = intent_node(state)
    constraints = result["parsed_constraints"]
    fields = [c["field"] for c in constraints]
    assert "diameter_inches" in fields or any("width" in f or "diameter" in f for f in fields)


def test_extracts_capacity_constraint():
    from agent.nodes.intent_node import intent_node
    state = make_state("umbrella base that holds a 15 foot umbrella")
    result = intent_node(state)
    constraints = result["parsed_constraints"]
    capacity_constraints = [c for c in constraints
                            if "umbrella" in c["field"].lower() or "capacity" in c["field"].lower()]
    assert len(capacity_constraints) > 0


def test_hard_vs_soft_constraint():
    from agent.nodes.intent_node import intent_node
    state = make_state("umbrella base under $200, preferably black")
    result = intent_node(state)
    hard = [c for c in result["parsed_constraints"] if c.get("is_hard")]
    assert len(hard) >= 1  # price should be hard


def test_detects_category():
    from agent.nodes.intent_node import intent_node
    state = make_state("kids building blocks for 5 year olds")
    result = intent_node(state)
    assert result["category"] in ["kids_toys", "toys"]


def test_handles_ambiguous_query():
    """Agent should not crash on vague queries"""
    from agent.nodes.intent_node import intent_node
    state = make_state("something for my patio")
    result = intent_node(state)
    assert result["category"] is not None or result["parsed_constraints"] is not None
