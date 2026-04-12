"""
Constraint retention metrics for multi-turn conversations.

Detects when the agent drops a constraint that was established in an earlier
turn. The IntentNode is instructed to accumulate constraints across turns, but
this is prompt-driven — this module validates that it actually does so.

Two modes for specifying expected constraints per turn:

  1. Cumulative (default) — each turn's `hard_constraints` are deltas that
     accumulate. Later values on the same field supersede earlier ones.
     Use for single-category conversations and intra-category constraint updates.

  2. Snapshot — a turn with `expected_constraints_snapshot` defines the exact
     set expected in parsed_constraints at that point, bypassing the cumulative
     union. Use for cross-category conversations where the expected set resets
     or restores depending on which category is currently in context.

Usage:
    from evals.metrics.constraint_retention import (
        expected_constraints_at_turn,
        check_retention,
        retention_report,
    )
"""


def expected_constraints_at_turn(turns: list, up_to_index: int) -> list:
    """
    Return the expected constraint set after `up_to_index` turns (0-based).

    If the target turn has an `expected_constraints_snapshot` key, that exact
    list is returned directly (snapshot mode).

    Otherwise, constraints from all turns up to and including the target are
    unioned with last-value-wins per field (cumulative mode). This correctly
    handles constraint updates like "under 50 lbs" → "actually, under 30 lbs".
    """
    target_turn = turns[up_to_index]

    # Snapshot mode — caller specified the exact expected set for this turn
    if "expected_constraints_snapshot" in target_turn:
        return target_turn["expected_constraints_snapshot"]

    # Cumulative mode — union of all hard_constraints up to this turn
    seen: dict[str, dict] = {}  # field → latest constraint
    for turn in turns[: up_to_index + 1]:
        for c in turn.get("hard_constraints", []):
            seen[c["field"]] = c
    return list(seen.values())


def check_retention(parsed_constraints: list, expected: list) -> dict:
    """
    Check whether parsed_constraints retains all fields in expected.

    Args:
        parsed_constraints: constraints extracted by IntentNode this turn
        expected: constraints that should be present (from expected_constraints_at_turn)

    Returns:
        {
          "retention_rate": float,   # 1.0 = all constraints retained
          "retained_fields": list,   # fields present in parsed_constraints
          "forgotten_fields": list,  # fields from expected that are absent
        }
    """
    if not expected:
        return {
            "retention_rate": 1.0,
            "retained_fields": [],
            "forgotten_fields": [],
        }

    parsed_fields = {c["field"] for c in parsed_constraints}
    retained = [c["field"] for c in expected if c["field"] in parsed_fields]
    forgotten = [c["field"] for c in expected if c["field"] not in parsed_fields]

    return {
        "retention_rate": len(retained) / len(expected),
        "retained_fields": retained,
        "forgotten_fields": forgotten,
    }


def retention_report(turn_results: list, query_spec: dict) -> dict:
    """
    Compute per-turn retention and overall forgetting rate for a multi-turn query.

    Args:
        turn_results: list of state dicts, one per turn (in order)
        query_spec: the canonical query spec with `turns` list

    Returns:
        {
          "query_id": str,
          "overall_retention_rate": float,
          "any_forgetting": bool,
          "turns": [
            {
              "turn_index": int,
              "query": str,
              "retention_rate": float,
              "forgotten_fields": list,
              "retained_fields": list,
            }
          ]
        }
    """
    turns_spec = query_spec.get("turns", [])
    per_turn = []

    for i, state in enumerate(turn_results):
        if i >= len(turns_spec):
            break
        expected = expected_constraints_at_turn(turns_spec, i)
        parsed = state.get("parsed_constraints", [])
        check = check_retention(parsed, expected)
        per_turn.append({
            "turn_index": i + 1,
            "query": turns_spec[i].get("query", ""),
            **check,
        })

    # Overall: use the final turn's retention (all constraints should survive)
    if per_turn:
        final = per_turn[-1]
        overall = final["retention_rate"]
        any_forgetting = any(t["forgotten_fields"] for t in per_turn)
    else:
        overall = 1.0
        any_forgetting = False

    return {
        "query_id": query_spec.get("id", "unknown"),
        "overall_retention_rate": overall,
        "any_forgetting": any_forgetting,
        "turns": per_turn,
    }
