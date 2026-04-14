"""
Ranking quality metrics for eval results.

All metrics use K = min(5, len(ranked_products)) to handle shallow result sets.

Relevance definition (binary):
  A product is relevant if it passes all hard constraints AND has a
  groundedness score >= 0.5.

Metrics:
  hit_rate_at_1    — 1.0 if the top result is relevant, else 0.0
  precision_at_k   — (# relevant in top K) / K
  recall_at_k      — (# relevant in top K) / max(1, total relevant)
  ndcg_at_k        — normalised discounted cumulative gain with binary relevance

Usage:
    from evals.metrics.ranking_metrics import (
        relevant_ids, hit_rate_at_1, precision_at_k, recall_at_k, ndcg_at_k,
        compute_ranking_metrics,
    )
"""
import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.nodes.constraint_check_node import check_constraint


# ── Relevance ──────────────────────────────────────────────────────────────────

def relevant_ids(result: dict) -> set:
    """
    Return the set of product IDs considered relevant for this result.

    A product is relevant if:
      1. It passes all hard constraints from the query spec.
      2. Its groundedness score (from groundedness_annotations) is >= 0.5.
    """
    query_spec = result.get("query_spec", {})
    hard = [c for c in query_spec.get("hard_constraints", []) if c.get("is_hard", True)]
    annotations = {
        a["product_id"]: a.get("score", 0.0)
        for a in result.get("groundedness_annotations", [])
        if "product_id" in a
    }

    rel = set()
    for product in result.get("ranked_products", []):
        pid = product.get("id")
        if not pid:
            continue
        passes_constraints = all(check_constraint(product, c)[0] for c in hard)
        grounded = annotations.get(pid, 1.0) >= 0.5  # default 1.0 if no annotation
        if passes_constraints and grounded:
            rel.add(pid)
    return rel


# ── Individual metrics ─────────────────────────────────────────────────────────

def hit_rate_at_1(ranked: list, relevant: set) -> float:
    """1.0 if the top result is relevant, else 0.0."""
    if not ranked:
        return 0.0
    return 1.0 if ranked[0].get("id") in relevant else 0.0


def precision_at_k(ranked: list, relevant: set, k: int) -> float:
    """Fraction of top-K results that are relevant."""
    if not ranked or k == 0:
        return 0.0
    top_k = ranked[:k]
    hits = sum(1 for p in top_k if p.get("id") in relevant)
    return hits / k


def recall_at_k(ranked: list, relevant: set, k: int) -> float:
    """Fraction of all relevant products that appear in top K."""
    if not relevant:
        return 1.0  # no relevant products → trivially satisfied
    if not ranked or k == 0:
        return 0.0
    top_k = ranked[:k]
    hits = sum(1 for p in top_k if p.get("id") in relevant)
    return hits / len(relevant)


def ndcg_at_k(ranked: list, relevant: set, k: int) -> float:
    """
    Normalised Discounted Cumulative Gain with binary relevance.
    IDCG = sum of 1/log2(i+2) for i in range(min(k, |relevant|)).
    """
    if not ranked or k == 0:
        return 0.0

    top_k = ranked[:k]
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, p in enumerate(top_k)
        if p.get("id") in relevant
    )

    ideal_hits = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    return dcg / idcg if idcg > 0 else 0.0


# ── Batch helper ───────────────────────────────────────────────────────────────

def compute_ranking_metrics(results: list) -> dict:
    """
    Compute avg hit_rate@1, precision@K, recall@K, ndcg@K over a list of results.
    K = min(5, len(ranked_products)) per result.
    """
    hr1_scores = []
    prec_scores = []
    rec_scores = []
    ndcg_scores = []

    for result in results:
        ranked = result.get("ranked_products", [])
        if not ranked:
            continue
        k = min(5, len(ranked))
        rel = relevant_ids(result)

        hr1_scores.append(hit_rate_at_1(ranked, rel))
        prec_scores.append(precision_at_k(ranked, rel, k))
        rec_scores.append(recall_at_k(ranked, rel, k))
        ndcg_scores.append(ndcg_at_k(ranked, rel, k))

    def _avg(lst):
        return sum(lst) / len(lst) if lst else None

    return {
        "avg_hit_rate_at_1": _avg(hr1_scores),
        "avg_precision_at_k": _avg(prec_scores),
        "avg_recall_at_k": _avg(rec_scores),
        "avg_ndcg_at_k": _avg(ndcg_scores),
    }
