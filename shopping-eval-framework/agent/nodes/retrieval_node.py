import json
import os

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "catalog")


def load_catalog(category: str) -> list:
    path = os.path.join(CATALOG_DIR, f"{category}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def retrieval_node(state: dict) -> dict:
    category = state.get("category", "unknown")
    products = load_catalog(category)

    # Filter to in_stock only — this is a guardrail
    in_stock = [p for p in products if p.get("in_stock", False)]

    # Return top 20 candidates (simple for now, can add embeddings later)
    return {
        **state,
        "candidate_products": in_stock[:20]
    }
