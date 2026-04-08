"""
Priority-ordered action list derived from failure_distribution() output.

Priority score = failure_rate × business_impact_weight × fixability_score

Business impact weights reflect user-trust damage from each failure mode:
  output_violations      10  guardrail breach — violating product reaches user
  hallucination           8  user receives fabricated spec claims
  out_of_stock_presented  7  user clicks through to an unavailable item
  missing_spec_failure    5  spec data gap causing false constraint rejection
  catalog_gap             5  valid query, no catalog match (solvable via data)
  no_results              4  unexpectedly empty response
  ranking_failure         3  suboptimal ordering, valid products exist
  impossible_constraints  1  user constraint physically impossible (not fixable)

Fixability scores (1–3):
  3 = straightforward code or data fix
  2 = prompt or catalog enrichment work needed
  1 = structural limitation, low ROI to fix
"""

from __future__ import annotations

_FAILURE_CONFIG: dict[str, dict] = {
    "output_violations": {
        "business_impact": 10,
        "fixability": 3,
        "recommended_action": (
            "Audit ConstraintCheckNode — hard constraint logic has a gap "
            "allowing violating products into ranked output."
        ),
        "expected_metric_impact": "constraint_satisfaction_rate ↑, top1_valid_rate ↑",
    },
    "hallucination": {
        "business_impact": 8,
        "fixability": 2,
        "recommended_action": (
            "Revise groundedness prompt to be more conservative on boolean/inferred "
            "specs; consider lowering the grounded score threshold."
        ),
        "expected_metric_impact": (
            "avg_groundedness ↑; no_valid_results_rate may ↑ (tighter filter)"
        ),
    },
    "out_of_stock_presented": {
        "business_impact": 7,
        "fixability": 3,
        "recommended_action": (
            "Verify RetrievalNode OOS filter is applied before ranking; "
            "add integration test for in_stock=False catalog entries."
        ),
        "expected_metric_impact": "oos_rate_top1 ↓, top1_valid_rate ↑",
    },
    "missing_spec_failure": {
        "business_impact": 5,
        "fixability": 2,
        "recommended_action": (
            "Enrich catalog spec fields for affected product category; "
            "or add graceful degradation when a required spec is absent."
        ),
        "expected_metric_impact": "no_valid_results_rate ↓, avg_groundedness ↑",
    },
    "catalog_gap": {
        "business_impact": 5,
        "fixability": 2,
        "recommended_action": (
            "Expand catalog coverage for the failing query category, "
            "or surface a 'no match' response with alternative suggestions."
        ),
        "expected_metric_impact": "no_valid_results_rate ↓",
    },
    "no_results": {
        "business_impact": 4,
        "fixability": 2,
        "recommended_action": (
            "Investigate why ranked_products is unexpectedly empty — "
            "check constraint check and ranking pipeline for edge cases."
        ),
        "expected_metric_impact": "no_valid_results_rate ↓",
    },
    "ranking_failure": {
        "business_impact": 3,
        "fixability": 2,
        "recommended_action": (
            "Review RankingNode scoring weights; add test cases for "
            "suboptimal ordering patterns."
        ),
        "expected_metric_impact": "top1_valid_rate ↑",
    },
    "impossible_constraints": {
        "business_impact": 1,
        "fixability": 1,
        "recommended_action": (
            "Detect impossible constraint combinations at IntentNode and "
            "inform the user immediately rather than returning empty results."
        ),
        "expected_metric_impact": "UX improvement only — core metrics unchanged",
    },
}

_DEFAULT_CONFIG = {
    "business_impact": 3,
    "fixability": 2,
    "recommended_action": "Investigate failure mode.",
    "expected_metric_impact": "TBD",
}


def prioritize(failures: dict[str, int], total: int) -> list[dict]:
    """
    Return a priority-ordered list of actions to address failure modes.

    Args:
        failures: {failure_mode: count} from failure_distribution()
        total:    total number of results evaluated (to compute rates)

    Returns:
        List of action dicts sorted by priority_score descending.
        'success' entries are excluded.
        Each dict contains:
          failure_mode, count, rate, priority_score,
          recommended_action, expected_metric_impact
    """
    if total == 0:
        return []

    actions = []
    for mode, count in failures.items():
        if mode == "success" or count == 0:
            continue
        cfg = _FAILURE_CONFIG.get(mode, _DEFAULT_CONFIG)
        rate = count / total
        score = rate * cfg["business_impact"] * cfg["fixability"]
        actions.append({
            "failure_mode": mode,
            "count": count,
            "rate": round(rate, 3),
            "priority_score": round(score, 3),
            "recommended_action": cfg["recommended_action"],
            "expected_metric_impact": cfg["expected_metric_impact"],
        })

    return sorted(actions, key=lambda x: -x["priority_score"])
