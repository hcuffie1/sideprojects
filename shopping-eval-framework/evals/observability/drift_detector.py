"""
Drift detection: compare current eval run scores against a 7-day baseline
fetched from Langfuse.

Usage:
    from evals.observability.drift_detector import get_baseline_scores, detect_drift

    baseline = get_baseline_scores(["groundedness", "top1_valid"], days_back=7)
    alerts = detect_drift(current_scores, baseline)
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

from evals.observability.langfuse_client import get_langfuse_api_client

DRIFT_THRESHOLD = 0.05  # 5% relative change triggers an alert

# True = higher is better; False = lower is better
_HIGHER_IS_BETTER: Dict[str, bool] = {
    "groundedness": True,
    "constraint_satisfaction": True,
    "top1_valid": True,
    "output_violations": False,
}


def get_baseline_scores(
    metric_names: List[str],
    days_back: int = 7,
) -> Dict[str, Optional[float]]:
    """
    Fetch average scores from Langfuse over the past `days_back` days.
    Returns a dict of {metric_name: average_value | None}.
    Returns all-None if Langfuse is not configured or the API call fails.
    """
    lf = get_langfuse_api_client()
    if lf is None:
        return {name: None for name in metric_names}

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    scores: Dict[str, Optional[float]] = {}

    for name in metric_names:
        try:
            result = lf.scores.get_many(
                name=name,
                from_timestamp=start,
                to_timestamp=end,
            )
            values = [s.value for s in result.data if s.value is not None]
            scores[name] = sum(values) / len(values) if values else None
        except Exception as e:
            print(f"[drift] Could not fetch baseline for '{name}': {e}")
            scores[name] = None

    return scores


def detect_drift(
    current: Dict[str, Optional[float]],
    baseline: Dict[str, Optional[float]],
) -> List[Dict]:
    """
    Compare current scores against baseline.
    Returns a list of drift alerts, sorted by severity then magnitude.

    Each alert dict:
        metric, current, baseline, relative_change, is_regression, severity
    """
    alerts = []
    for metric, cur in current.items():
        base = baseline.get(metric)
        if base is None or cur is None or base == 0:
            continue

        rel = (cur - base) / base
        higher_is_better = _HIGHER_IS_BETTER.get(metric, True)
        is_regression = (
            (higher_is_better and rel < -DRIFT_THRESHOLD)
            or (not higher_is_better and rel > DRIFT_THRESHOLD)
        )

        if abs(rel) > DRIFT_THRESHOLD:
            alerts.append({
                "metric": metric,
                "current": round(cur, 3),
                "baseline": round(base, 3),
                "relative_change": round(rel, 3),
                "is_regression": is_regression,
                "severity": "HIGH" if is_regression else "INFO",
            })

    return sorted(
        alerts,
        key=lambda x: (0 if x["is_regression"] else 1, -abs(x["relative_change"])),
    )
