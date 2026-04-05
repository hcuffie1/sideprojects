"""
Insights generator — takes computed metrics + failure distribution and
produces a structured dict with a plain-English summary and recommendations.

Pass threshold:
  top1_valid_rate  >= 0.8
  avg_groundedness >= 0.7

Usage:
    from evals.insights.analyze_results import analyze
    insights = analyze(metrics, failures)
"""

PASS_THRESHOLD = {
    "top1_valid_rate": 0.8,
    "avg_groundedness": 0.7,
}

RECOMMENDATIONS = {
    "out_of_stock_presented": (
        "Fix guardrail: in-stock filter is not blocking OOS products "
        "before they reach the response node."
    ),
    "constraint_violation": (
        "Improve constraint_check_node: hard constraints are not being "
        "enforced before ranking."
    ),
    "hallucination": (
        "Increase groundedness threshold or improve product spec coverage "
        "so LLM claims can always be verified."
    ),
    "missing_spec_failure": (
        "Enrich catalog specs — key fields are absent, causing constraint "
        "verification to fail by default."
    ),
    "no_results": (
        "Review retrieval and constraint logic: valid queries are returning "
        "no candidates."
    ),
    "ranking_failure": (
        "Audit ranking_node scoring — best valid products are not reaching "
        "the top position."
    ),
    "success": "Agent is performing within expected thresholds.",
}


def _top_failure(failures: dict) -> str | None:
    non_success = {k: v for k, v in failures.items() if k != "success"}
    if not non_success:
        return None
    return max(non_success, key=lambda k: non_success[k])


def _passes(metrics: dict) -> bool:
    for key, threshold in PASS_THRESHOLD.items():
        value = metrics.get(key)
        if value is None:
            continue
        if value < threshold:
            return False
    return True


def analyze(metrics: dict, failures: dict) -> dict:
    """
    Return a structured insights dict:
    {
        "pass": bool,
        "top_failure_mode": str | None,
        "recommendations": [str],
        "summary": str,
    }
    """
    passed = _passes(metrics)
    top_mode = _top_failure(failures)
    recommendations = []

    if top_mode:
        recommendations.append(RECOMMENDATIONS.get(top_mode, ""))

    # Additional recommendations based on metric thresholds
    if (
        metrics.get("avg_groundedness") is not None
        and metrics["avg_groundedness"] < PASS_THRESHOLD["avg_groundedness"]
    ):
        rec = RECOMMENDATIONS["hallucination"]
        if rec not in recommendations:
            recommendations.append(rec)

    if (
        metrics.get("oos_rate_top1") is not None
        and metrics["oos_rate_top1"] > 0
    ):
        rec = RECOMMENDATIONS["out_of_stock_presented"]
        if rec not in recommendations:
            recommendations.append(rec)

    status = "PASS" if passed else "FAIL"
    top_str = top_mode or "none"
    n = metrics.get("n", "?")
    summary = (
        f"{status} — {n} queries evaluated. "
        f"top1_valid_rate={metrics.get('top1_valid_rate', 'N/A'):.2f}, "
        f"avg_groundedness={metrics.get('avg_groundedness', 'N/A'):.2f}. "
        f"Top failure mode: {top_str}."
    )

    return {
        "pass": passed,
        "top_failure_mode": top_mode,
        "recommendations": recommendations,
        "summary": summary,
    }
