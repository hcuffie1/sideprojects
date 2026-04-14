"""
Champion / Challenger A/B comparison runner.

Runs the same benchmark query set through two ranking configurations and
outputs a side-by-side metric comparison table.

Champion and challenger run in parallel (ThreadPoolExecutor) to halve wall-clock
time. Results are tagged in Langfuse for post-hoc filtering.

Usage:
    python scripts/run_ab_comparison.py                # 5-query sample, parallel
    python scripts/run_ab_comparison.py --full         # all 27 single-turn queries
    python scripts/run_ab_comparison.py --sample 10    # custom sample size
    python scripts/run_ab_comparison.py --version-prefix my_exp
"""
import sys
import os
import argparse
import time
import uuid
import yaml
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from langfuse import observe, get_client  # noqa: E402

from agent.graph import agent  # noqa: E402
from agent.nodes.ranking_node import ranking_node as _original_ranking_node  # noqa: E402
from agent.nodes.constraint_check_node import check_constraint  # noqa: E402
from evals.canonical_queries import CANONICAL_QUERIES  # noqa: E402
from evals.metrics.compute_metrics import compute_metrics  # noqa: E402
from evals.metrics.ranking_metrics import compute_ranking_metrics  # noqa: E402
from evals.metrics.failure_analysis import classify_failure  # noqa: E402
from evals.pricing import cost_for_tokens  # noqa: E402

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIGS_PATH = os.path.join(_PROJECT_ROOT, "configs", "ranking_configs.yaml")
_OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "docs", "ab_comparison.md")

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
    "_token_usage": None,
    "user_id": None,
}


def _load_configs() -> dict:
    with open(_CONFIGS_PATH) as f:
        return yaml.safe_load(f)


def _select_queries(full: bool, sample_n: int) -> list:
    single_turn = [q for q in CANONICAL_QUERIES if q.get("type") != "multi_turn"]
    if full:
        return single_turn
    # Deterministic sample: pick evenly across query types
    random.seed(42)
    return random.sample(single_turn, min(sample_n, len(single_turn)))


@observe()
def _run_query_with_config(
    query_spec: dict,
    ranking_weights: dict,
    version_tag: str,
    run_id: str,
) -> dict:
    """Run a single query with a specific ranking config. Tagged for Langfuse."""
    get_client().update_current_span(
        name=f"ab-{query_spec['id']}-{version_tag}",
        input={"query": query_spec["query"]},
        metadata={
            "query_id": query_spec["id"],
            "agent_version": version_tag,
            "run_id": run_id,
            "ranking_weights": ranking_weights,
            "tags": ["ab_comparison", version_tag],
        },
    )

    t0 = time.perf_counter()
    # Invoke agent — ranking_node reads config from state via _ranking_config key
    state = {**EMPTY_STATE, "query": query_spec["query"], "_ranking_config": ranking_weights}
    result = agent.invoke(state)
    latency_ms = (time.perf_counter() - t0) * 1000

    result["query_spec"] = query_spec
    result["_latency_ms"] = latency_ms

    token_usage = result.get("_token_usage") or {}
    in_tok = token_usage.get("input_total", 0)
    out_tok = token_usage.get("output_total", 0)
    get_client().update_current_span(
        output={"response": result.get("final_response", "")[:200]},
        metadata={
            "failure_mode": classify_failure(result),
            "latency_ms": round(latency_ms, 1),
            "tokens_input": in_tok,
            "tokens_output": out_tok,
            "cost_usd": round(cost_for_tokens(in_tok, out_tok), 6),
        },
    )
    return result


def _run_arm(queries: list, weights: dict, version_tag: str, run_id: str) -> list:
    """Run all queries for one arm (champion or challenger)."""
    results = []
    for q in queries:
        try:
            result = _run_query_with_config(q, weights, version_tag, run_id)
            results.append(result)
        except Exception as e:
            print(f"  ERROR [{version_tag}] {q['id']}: {e}")
    return results


def _aggregate(results: list) -> dict:
    """Compute all comparison metrics over a result set."""
    base = compute_metrics(results)
    ranking = compute_ranking_metrics(results)

    latencies = [r["_latency_ms"] for r in results if r.get("_latency_ms")]
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    token_totals = [
        (r.get("_token_usage") or {})
        for r in results
    ]
    in_tokens = [t.get("input_total", 0) for t in token_totals]
    out_tokens = [t.get("output_total", 0) for t in token_totals]
    avg_cost = (
        cost_for_tokens(sum(in_tokens), sum(out_tokens)) / len(results)
        if results else None
    )

    return {
        **base,
        **ranking,
        "avg_latency_ms": avg_latency,
        "avg_cost_usd": avg_cost,
    }


def _fmt_val(v, fmt: str = "{:.3f}") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return fmt.format(v)
    return str(v)


def _fmt_delta(c_val, ch_val, fmt: str = "{:+.3f}") -> str:
    if c_val is None or ch_val is None:
        return "N/A"
    delta = ch_val - c_val
    if isinstance(c_val, float):
        return fmt.format(delta)
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta}"


# (key, label, value_format, delta_format)
_TABLE_ROWS = [
    ("avg_hit_rate_at_1",          "Hit Rate@1",            "{:.3f}",   "{:+.3f}"),
    ("avg_precision_at_k",         "Precision@K",           "{:.3f}",   "{:+.3f}"),
    ("avg_recall_at_k",            "Recall@K",              "{:.3f}",   "{:+.3f}"),
    ("avg_ndcg_at_k",              "NDCG@K",                "{:.3f}",   "{:+.3f}"),
    ("constraint_satisfaction_rate","Constraint Sat. Rate", "{:.3f}",   "{:+.3f}"),
    ("avg_groundedness",           "Avg Groundedness",      "{:.3f}",   "{:+.3f}"),
    ("avg_citation_accuracy",      "Avg Citation Accuracy", "{:.3f}",   "{:+.3f}"),
    ("avg_latency_ms",             "Avg Latency (ms)",      "{:.1f}",   "{:+.1f}"),
    ("avg_cost_usd",               "Avg Cost/Query ($)",    "${:.6f}",  "${:+.6f}"),
]


_PRIMARY_METRICS = [
    "constraint_satisfaction_rate",
    "avg_groundedness",
    "avg_citation_accuracy",
    "avg_hit_rate_at_1",
]
_COST_METRICS = ["avg_latency_ms", "avg_cost_usd"]
_MIN_DELTA = 0.02   # smaller delta is noise
_MIN_COST_DELTA_PCT = 0.05   # <5% cost/latency difference = tie


def declare_winner(champ: dict, chall: dict, n_queries: int) -> dict:
    """
    Compare champion vs challenger and return a structured verdict.

    Returns:
        verdict str, champion_wins, challenger_wins, ties,
        decisive_metrics list, recommendation str
    """
    champion_wins = 0
    challenger_wins = 0
    ties = 0
    decisive: list = []

    for metric in _PRIMARY_METRICS:
        c, ch = champ.get(metric), chall.get(metric)
        if c is None or ch is None:
            ties += 1
            continue
        delta = ch - c
        if abs(delta) < _MIN_DELTA:
            ties += 1
        elif delta > 0:
            challenger_wins += 1
            decisive.append(f"{metric}: {delta:+.3f} for challenger")
        else:
            champion_wins += 1
            decisive.append(f"{metric}: {abs(delta):+.3f} for champion")

    for metric in _COST_METRICS:
        c, ch = champ.get(metric), chall.get(metric)
        if c is None or ch is None:
            ties += 1
            continue
        baseline = max(abs(c), 1e-9)
        if abs(ch - c) / baseline < _MIN_COST_DELTA_PCT:
            ties += 1
        elif ch < c:
            challenger_wins += 1
        else:
            champion_wins += 1

    if champion_wins == 0 and challenger_wins == 0:
        verdict = "NO_WINNER"
        recommendation = (
            "No meaningful differentiation detected. The two ranking configs "
            "likely produce identical product orderings — possibly because most "
            "queries return only 1–2 valid results, leaving nothing to rerank. "
            "Try: (1) --full to use all 27 queries, (2) a more aggressive "
            "challenger config (e.g. spec_completeness: 0.2, soft_constraint_bonus: 0.8), "
            "(3) adding catalog items so more products pass constraint checking."
        )
    elif challenger_wins > champion_wins:
        verdict = "CHALLENGER WINS"
        recommendation = f"Promote challenger. Decisive wins: {'; '.join(decisive)}."
    elif champion_wins > challenger_wins:
        verdict = "CHAMPION WINS"
        recommendation = f"Keep champion. Decisive wins: {'; '.join(decisive)}."
    else:
        verdict = "INCONCLUSIVE"
        recommendation = "Tied on primary metrics. Expand query set or widen config delta before deciding."

    return {
        "verdict": verdict,
        "champion_wins": champion_wins,
        "challenger_wins": challenger_wins,
        "ties": ties,
        "decisive_metrics": decisive,
        "n_queries": n_queries,
        "recommendation": recommendation,
    }


def _build_table(champ: dict, chall: dict, champ_name: str, chall_name: str) -> str:
    col_w = max(len(champ_name), len(chall_name), 12)
    header = (
        f"{'Metric':<28} | {champ_name:^{col_w}} | "
        f"{chall_name:^{col_w}} | {'Delta':^12}"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for key, label, val_fmt, delta_fmt in _TABLE_ROWS:
        c_val = champ.get(key)
        ch_val = chall.get(key)
        lines.append(
            f"{label:<28} | {_fmt_val(c_val, val_fmt):^{col_w}} | "
            f"{_fmt_val(ch_val, val_fmt):^{col_w}} | "
            f"{_fmt_delta(c_val, ch_val, delta_fmt):^12}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Run all 27 single-turn queries (default: sample of 5)")
    parser.add_argument("--sample", type=int, default=5,
                        help="Number of queries in sample mode (default: 5)")
    parser.add_argument("--version-prefix", default="ab",
                        help="Prefix for Langfuse version tags (default: ab)")
    args = parser.parse_args()

    configs = _load_configs()
    champ_cfg = configs["champion"]
    chall_cfg = configs["challenger"]
    champ_tag = f"{args.version_prefix}_champion"
    chall_tag = f"{args.version_prefix}_challenger"

    queries = _select_queries(full=args.full, sample_n=args.sample)
    run_id = str(uuid.uuid4())[:8]

    n = len(queries)
    print(f"\nA/B Comparison — {n} queries, running champion + challenger in parallel")
    print(f"  Champion:   {champ_cfg['name']}  (weights: {champ_cfg['weights']})")
    print(f"  Challenger: {chall_cfg['name']}  (weights: {chall_cfg['weights']})")
    print(f"  Run ID: {run_id}\n")

    champ_results: list = []
    chall_results: list = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_champ = pool.submit(
            _run_arm, queries, champ_cfg["weights"], champ_tag, run_id
        )
        fut_chall = pool.submit(
            _run_arm, queries, chall_cfg["weights"], chall_tag, run_id
        )
        for fut in as_completed([fut_champ, fut_chall]):
            if fut is fut_champ:
                champ_results = fut.result()
                print(f"  Champion done ({len(champ_results)} results)")
            else:
                chall_results = fut.result()
                print(f"  Challenger done ({len(chall_results)} results)")

    champ_agg = _aggregate(champ_results)
    chall_agg = _aggregate(chall_results)

    table = _build_table(champ_agg, chall_agg, champ_cfg["name"], chall_cfg["name"])
    verdict = declare_winner(champ_agg, chall_agg, n)

    print(f"\n{'='*70}")
    print("A/B COMPARISON RESULTS")
    print(f"{'='*70}")
    print(table)
    print(f"{'='*70}")
    print(f"\nVERDICT: {verdict['verdict']}")
    print(f"  Champion wins: {verdict['champion_wins']}  |  "
          f"Challenger wins: {verdict['challenger_wins']}  |  Ties: {verdict['ties']}")
    if verdict["decisive_metrics"]:
        print("  Decisive metrics:")
        for dm in verdict["decisive_metrics"]:
            print(f"    - {dm}")
    print(f"  Recommendation: {verdict['recommendation']}\n")

    # Save to docs/ab_comparison.md
    os.makedirs(os.path.dirname(_OUTPUT_PATH), exist_ok=True)
    with open(_OUTPUT_PATH, "w") as f:
        f.write(f"# A/B Comparison: {champ_cfg['name']} vs {chall_cfg['name']}\n\n")
        f.write(f"- **Queries:** {n} ({'full suite' if args.full else f'sample of {args.sample}'})\n")
        f.write(f"- **Run ID:** `{run_id}`\n")
        f.write(f"- **Champion weights:** `{champ_cfg['weights']}`\n")
        f.write(f"- **Challenger weights:** `{chall_cfg['weights']}`\n\n")
        f.write("```\n")
        f.write(table)
        f.write("\n```\n\n")
        f.write(f"## Verdict: {verdict['verdict']}\n\n")
        f.write(f"- Champion wins: {verdict['champion_wins']}\n")
        f.write(f"- Challenger wins: {verdict['challenger_wins']}\n")
        f.write(f"- Ties: {verdict['ties']}\n")
        if verdict["decisive_metrics"]:
            f.write("- Decisive metrics:\n")
            for dm in verdict["decisive_metrics"]:
                f.write(f"  - {dm}\n")
        f.write(f"\n**Recommendation:** {verdict['recommendation']}\n")

    print(f"Saved: {_OUTPUT_PATH}")
    get_client().flush()


if __name__ == "__main__":
    main()
