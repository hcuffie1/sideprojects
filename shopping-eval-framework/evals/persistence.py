"""
SQLite persistence for eval results.

After each query run, call save_result() to write one row to traces.db.
Rows from the same script invocation share a run_id (UUID).

DB location: .eval_results/traces.db  (relative to project root, gitignored)

Key columns:
  candidates_eliminated  — products removed by constraint_check_node
                           (high = guardrail working correctly)
  output_violations      — ranked products that violated a hard constraint
                           (should always be 0; > 0 = guardrail failure)
  constraint_violations_json — full violation log from filtering stage

Usage:
    from evals.persistence import init_db, save_result
    import uuid

    run_id = str(uuid.uuid4())
    init_db()
    # ... run queries ...
    save_result(result, run_id)
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

from evals.metrics.failure_analysis import classify_failure

# Resolve path relative to project root (two levels up from this file)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, ".eval_results", "traces.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                      TEXT NOT NULL,
    query_id                    TEXT,
    query_text                  TEXT,
    query_type                  TEXT,
    timestamp                   TEXT NOT NULL,
    category_detected           TEXT,
    failure_mode                TEXT,
    num_ranked                  INTEGER,
    top1_in_stock               INTEGER,
    top1_valid                  INTEGER,
    avg_groundedness            REAL,
    candidates_eliminated       INTEGER,
    output_violations           INTEGER,
    constraint_violations_json  TEXT,
    metrics_json                TEXT
)
"""

# Columns added after initial release — applied via ALTER TABLE if missing.
# Order matters: add before renaming so both old and new names are handled.
_MIGRATION_COLUMNS = [
    ("constraint_violations_json", "TEXT"),
    ("candidates_eliminated", "INTEGER"),
    ("output_violations", "INTEGER"),
]

_OPS = {
    "lte": lambda a, b: a <= b,
    "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
    "contains": lambda a, b: b in str(a),
}


def init_db(db_path: str = DB_PATH) -> None:
    """Create the .eval_results directory and traces table; migrate if needed."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(CREATE_TABLE_SQL)
        # Add any new columns that weren't in the original schema
        for col_name, col_type in _MIGRATION_COLUMNS:
            try:
                conn.execute(
                    f"ALTER TABLE traces ADD COLUMN {col_name} {col_type}"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()


def _top1_valid(result: dict) -> int | None:
    """Return 1 if top ranked product passes all hard constraints + in stock."""
    ranked = result.get("ranked_products", [])
    if not ranked:
        return None
    top = ranked[0]
    if not top.get("in_stock"):
        return 0
    query_spec = result.get("query_spec", {})
    for c in query_spec.get("hard_constraints", []):
        if not c.get("is_hard", True):
            continue
        field = c["field"]
        op = c["op"]
        value = c["value"]
        specs = top.get("specs", {})
        actual = specs.get(field, top.get(field))
        if actual is None:
            return 0
        if op in _OPS and not _OPS[op](actual, value):
            return 0
    return 1


def _output_violations(result: dict) -> int:
    """
    Count ranked products that violate at least one hard constraint.
    Should always be 0 — > 0 means constraint_check_node failed to filter.
    """
    ranked = result.get("ranked_products", [])
    query_spec = result.get("query_spec", {})
    hard_constraints = [
        c for c in query_spec.get("hard_constraints", [])
        if c.get("is_hard", True)
    ]
    if not hard_constraints:
        return 0

    count = 0
    for product in ranked:
        for c in hard_constraints:
            field = c["field"]
            op = c["op"]
            value = c["value"]
            specs = product.get("specs", {})
            actual = specs.get(field, product.get(field))
            if actual is None or (op in _OPS and not _OPS[op](actual, value)):
                count += 1
                break  # one violation per product is enough
    return count


def _avg_groundedness(result: dict) -> float | None:
    scores = [
        a["score"]
        for a in result.get("groundedness_annotations", [])
        if "score" in a
    ]
    return sum(scores) / len(scores) if scores else None


def _query_text(result: dict) -> str:
    """For single-turn, use query. For multi-turn, use first turn query."""
    query_spec = result.get("query_spec", {})
    if query_spec.get("type") == "multi_turn":
        turns = query_spec.get("turns", [])
        return turns[0]["query"] if turns else ""
    return query_spec.get("query", result.get("query", ""))


def save_result(result: dict, run_id: str, db_path: str = DB_PATH) -> None:
    """Write one query result as a row in traces."""
    query_spec = result.get("query_spec", {})
    ranked = result.get("ranked_products", [])
    top = ranked[0] if ranked else None
    violations = result.get("constraint_violations", [])

    row = {
        "run_id": run_id,
        "query_id": query_spec.get("id"),
        "query_text": _query_text(result),
        "query_type": query_spec.get("query_type"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category_detected": result.get("category"),
        "failure_mode": classify_failure(result),
        "num_ranked": len(ranked),
        "top1_in_stock": int(top["in_stock"]) if top else None,
        "top1_valid": _top1_valid(result),
        "avg_groundedness": _avg_groundedness(result),
        "candidates_eliminated": len(violations),
        "output_violations": _output_violations(result),
        "constraint_violations_json": json.dumps(violations),
        "metrics_json": json.dumps({
            "parsed_constraints": result.get("parsed_constraints", []),
            "groundedness_annotations": result.get(
                "groundedness_annotations", []
            ),
            "agent_rationale": result.get("agent_rationale"),
        }),
    }

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces (
                run_id, query_id, query_text, query_type, timestamp,
                category_detected, failure_mode, num_ranked,
                top1_in_stock, top1_valid, avg_groundedness,
                candidates_eliminated, output_violations,
                constraint_violations_json, metrics_json
            ) VALUES (
                :run_id, :query_id, :query_text, :query_type, :timestamp,
                :category_detected, :failure_mode, :num_ranked,
                :top1_in_stock, :top1_valid, :avg_groundedness,
                :candidates_eliminated, :output_violations,
                :constraint_violations_json, :metrics_json
            )
            """,
            row,
        )
        conn.commit()
