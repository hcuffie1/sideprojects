"""
Phase 2 integration tests: run the full agent on each single-turn canonical
query and assert against expected outcomes.

These tests make real LLM calls (~$0.01–0.05 per run). Run with:
    pytest evals/phase2/test_canonical_queries.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from dotenv import load_dotenv

load_dotenv()

from agent.graph import agent
from evals.canonical_queries import CANONICAL_QUERIES

SINGLE_TURN = [
    q for q in CANONICAL_QUERIES if q.get("type") != "multi_turn"
]

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


def run_single(query_spec: dict) -> dict:
    return agent.invoke({**EMPTY_STATE, "query": query_spec["query"]})


@pytest.mark.parametrize("query_spec", SINGLE_TURN, ids=[q["id"] for q in SINGLE_TURN])
def test_category_detected(query_spec):
    result = run_single(query_spec)
    expected = query_spec.get("expected_category")
    if expected:
        assert result["category"] == expected, (
            f"[{query_spec['id']}] Expected category '{expected}', "
            f"got '{result['category']}'"
        )


@pytest.mark.parametrize("query_spec", SINGLE_TURN, ids=[q["id"] for q in SINGLE_TURN])
def test_ranked_products_in_stock(query_spec):
    if query_spec.get("expected_no_products_found"):
        pytest.skip("No products expected for this query")
    result = run_single(query_spec)
    for p in result.get("ranked_products", []):
        assert p.get("in_stock"), (
            f"[{query_spec['id']}] Out-of-stock product in ranked results: "
            f"{p.get('id')}"
        )


@pytest.mark.parametrize("query_spec", SINGLE_TURN, ids=[q["id"] for q in SINGLE_TURN])
def test_no_hallucination(query_spec):
    if not query_spec.get("expected_no_hallucination"):
        pytest.skip("Hallucination check not expected for this query")
    result = run_single(query_spec)
    annotations = result.get("groundedness_annotations", [])
    for a in annotations:
        assert a.get("score", 1.0) > 0.5, (
            f"[{query_spec['id']}] Low groundedness score "
            f"({a.get('score')}) for product {a.get('product_id')}"
        )


@pytest.mark.parametrize("query_spec", SINGLE_TURN, ids=[q["id"] for q in SINGLE_TURN])
def test_impossible_query_handled(query_spec):
    if not query_spec.get("expected_no_products_found"):
        pytest.skip("This query is expected to return results")
    result = run_single(query_spec)
    assert result.get("ranked_products") == [], (
        f"[{query_spec['id']}] Expected no ranked products for impossible query"
    )
    response = result.get("final_response", "").lower()
    no_results_phrases = ["wasn't able", "unable to find", "no products", "couldn't find"]
    assert any(p in response for p in no_results_phrases), (
        f"[{query_spec['id']}] Response didn't indicate no results found: "
        f"{result.get('final_response')}"
    )
