import json
import os
from difflib import get_close_matches
from agent.tracing import traced_node

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "catalog")


def load_catalog(category: str) -> list:
    path = os.path.join(CATALOG_DIR, f"{category}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _normalize_constraint_fields(constraints: list, products: list) -> list:
    """
    Remap any constraint field name that doesn't exactly match a catalog spec
    key to the closest matching key (by string similarity, cutoff=0.6).

    This handles the schema alignment problem: IntentNode generates field names
    from natural language (e.g. 'width_inches'), but ConstraintCheckNode does
    exact string matching against catalog spec keys ('diameter_inches'). When
    they diverge, all products fail with spec_missing and ranked_products=[].

    Fields that already match exactly are left unchanged. Fields with no close
    match are also left unchanged (they will fail constraint check as before).
    """
    if not products or not constraints:
        return constraints

    valid_fields = {
        key
        for p in products
        for key in p.get("specs", {}).keys()
    }

    normalized = []
    for c in constraints:
        if c["field"] not in valid_fields:
            matches = get_close_matches(c["field"], valid_fields, n=1, cutoff=0.6)
            if matches:
                c = {**c, "field": matches[0]}
        normalized.append(c)
    return normalized


@traced_node("RetrievalNode")
def retrieval_node(state: dict) -> dict:
    category = state.get("category", "unknown")
    products = load_catalog(category)

    # Filter to in_stock only — this is a guardrail
    in_stock = [p for p in products if p.get("in_stock", False)]

    # Normalize constraint field names against actual catalog spec keys
    constraints = _normalize_constraint_fields(
        state.get("parsed_constraints", []), in_stock
    )

    # Return top 20 candidates (simple for now, can add embeddings later)
    return {
        **state,
        "candidate_products": in_stock[:20],
        "parsed_constraints": constraints,
    }
