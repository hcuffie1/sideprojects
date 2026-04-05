"""Run the full agent on all canonical queries and print results."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import agent

NON_CANONICAL_QUERIES = [
    {
        "id": "q_006",
        "query": "patio umbrella base that's less than 20 bucks",  # only dollar constraint
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "price", "op": "lte", "value": 20}
        ],
        "expected_top_result_in_stock": False,
        "expected_no_hallucination": True,
        "description": "Impossible constraints given catalog"
    }
]

def run_query(query_spec: dict) -> dict:
    print(f"\n{'='*60}")
    print(f"[{query_spec['id']}] {query_spec['description']}")
    print(f"Query: {query_spec['query']}")
    print("-" * 60)

    result = agent.invoke({
        "query": query_spec["query"],
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
    })

    print(f"Category detected: {result.get('category')}")
    print(f"Constraints parsed: {len(result.get('parsed_constraints', []))}")
    print(f"Candidates retrieved: {len(result.get('candidate_products', []))}")
    print(f"After constraint check: {len(result.get('filtered_products', []))}")
    print(f"After ranking (top 5): {len(result.get('ranked_products', []))}")
    print(f"Violations: {len(result.get('constraint_violations', []))}")
    print(f"\nRationale: {result.get('agent_rationale')}")
    print(f"\nResponse:\n{result.get('final_response')}")

    return result


if __name__ == "__main__":
    query_ids = sys.argv[1:] if len(sys.argv) > 1 else None

    for q in NON_CANONICAL_QUERIES:
        if query_ids and q["id"] not in query_ids:
            continue
        try:
            run_query(q)
        except Exception as e:
            print(f"ERROR on {q['id']}: {e}")
