# Shopping Agent Eval Framework

A production-style evaluation framework for a multi-turn conversational shopping agent built with LangGraph + Gemini. Demonstrates the full lifecycle of eval-driven agent development: guardrail design, constraint checking, groundedness scoring, Langfuse-managed prompt versioning, SQLite-backed persistence, and Langfuse observability with drift detection.

---

## Architecture

A 6-node LangGraph agent processes shopping queries through a deterministic pipeline:

```
User Query
    │
    ▼
IntentNode          → extracts hard/soft constraints from natural language
    │
    ▼
RetrievalNode       → loads catalog, filters out-of-stock products
    │
    ▼
ConstraintCheckNode → rule-based hard constraint enforcement (missing spec = violation)
    │
    ▼
RankingNode         → scores by spec completeness + soft constraint satisfaction
    │
    ▼
GroundednessNode    → LLM verifies each spec claim is actually supported by data
    │
    ▼
ResponseNode        → only recommends products with groundedness score > 0.5
```

Supports both single-turn and multi-turn (stateful conversation) queries.

---

## Evaluation layers

### Phase 1 — Unit tests (no eval API key needed)
Fast pytest suite covering each node in isolation:

| Test file | What it catches |
|---|---|
| `test_constraint_checking.py` | Hard constraint enforcement, missing-spec-as-violation |
| `test_retrieval.py` | Out-of-stock filtering |
| `test_ranking.py` | Spec completeness scoring, soft constraint weighting |
| `test_groundedness.py` | **The confident fabricator test** (see below) |
| `test_intent_extraction.py` | Constraint extraction from natural language |
| `test_response_generation.py` | Response only includes grounded products |

`test_groundedness.py` includes a secondary `test_deepeval_hallucination_metric` that uses DeepEval's `HallucinationMetric` (LLM-jury method) as an independent cross-check. Our GroundednessNode checks spec-by-spec for missing fields; DeepEval prompts an LLM to judge whether a response is supported by the provided context. Agreement validates the approach; divergence is a signal worth investigating.

### Phase 2 — Integration tests
End-to-end tests against the full LangGraph pipeline:

| Test file | What it covers |
|---|---|
| `test_canonical_queries.py` | All 23 canonical queries, metric thresholds |
| `test_multiturn.py` | Stateful multi-turn conversation across query types |

### Phase 3 — Observability (Langfuse)
Every eval run is instrumented with full traces:
- **Span-level traces**: each of the 6 nodes appears as a child span in Langfuse
- **4 scores per trace**: `groundedness`, `constraint_satisfaction`, `top1_valid`, `output_violations`
- **Human review queue**: traces with violations or low groundedness are flagged via `needs_human_review` score
- **Drift detection**: `weekly_report.py` compares current run to 7-day Langfuse baseline (5% threshold)
- **A/A' comparison**: `--version` flag tags traces for side-by-side model comparison
- **SQLite persistence**: every run saved to `.eval_results/traces.db` with `langfuse_trace_id` for cross-referencing

### Phase 4 — Prompt versioning (Langfuse)
All LLM prompts are managed through Langfuse for version-controlled, deployment-free iteration:
- **Canonical registry**: `agent/prompts.py` defines all 3 prompts (`intent-extraction`, `groundedness-check`, `response-generation`) with `{{double_brace}}` variable syntax
- **Runtime fetch**: nodes call `compile_to_messages(name, **kwargs)` which fetches `label="production"` from Langfuse (60s TTL cache) — edits in the Langfuse UI take effect without a deploy
- **Version attribution**: each node logs `prompt_name` + `prompt_version` to its Langfuse span, so every trace shows which prompt version produced it
- **Local fallback**: `_LocalPrompt` mirrors the same `.compile()` API when `LANGFUSE_PUBLIC_KEY` is not set — all tests pass without Langfuse credentials
- **Seed script**: `scripts/seed_prompts.py` bootstraps or updates prompts in Langfuse

---

## The key test

```bash
pytest evals/phase1/test_groundedness.py::test_no_confident_fabrication -v
```

Catches the **confident fabricator** failure mode: an agent claiming a product can hold a 15-foot umbrella when the product spec contains no `max_umbrella_size_feet` field. The agent must score this < 0.5 (not grounded). This mirrors a known production failure pattern in shopping agents that hallucinate product capabilities from vague description text.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file:
```
GEMINI_API_KEY=your_gemini_key

# Optional — enables Langfuse tracing, drift detection, and prompt management
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

If using Langfuse, bootstrap prompts once after setup:
```bash
python scripts/seed_prompts.py        # register all 3 prompts with label=production
python scripts/seed_prompts.py --check  # verify current versions without writing
```

---

## Running

```bash
# Logic-only tests (no API key needed, fast)
pytest evals/phase1/test_constraint_checking.py evals/phase1/test_retrieval.py evals/phase1/test_ranking.py -v

# The fabricator test (requires GEMINI_API_KEY)
pytest evals/phase1/test_groundedness.py::test_no_confident_fabrication -v

# Full Phase 1 test suite
pytest evals/phase1/ -v

# Full integration test suite
pytest evals/phase2/ -v

# Run evals interactively
python scripts/run_evals.py                     # all 23 queries
python scripts/run_evals.py --mode dev          # single query (q_001), fast iteration
python scripts/run_evals.py --mode sample       # first 3 single-turn queries
python scripts/run_evals.py q_001 q_003         # specific query IDs
python scripts/run_evals.py --version v1_prime  # tag for A/A' comparison in Langfuse

# Weekly report with drift detection
python scripts/weekly_report.py

# Interactive chat
python scripts/chat.py

# Prompt management
python scripts/seed_prompts.py                # bootstrap prompts (run once)
python scripts/seed_prompts.py --force        # push a new version to Langfuse
python scripts/seed_prompts.py --check        # print current versions, no writes
```

### Prompt iteration workflow

```
1. Edit prompt text in agent/prompts.py  →  PROMPT_DEFINITIONS
2. python scripts/seed_prompts.py --force   →  new version created in Langfuse
3. python scripts/run_evals.py --version v3  →  runs tagged with new version
4. Compare avg_groundedness between versions in Langfuse dashboard
   (filter by prompt_version in span metadata)
```

Alternatively, edit the prompt directly in the Langfuse UI and promote to
`label="production"` — the agent picks it up within 60 seconds, no deploy needed.

---

## Canonical query suite (23 queries)

Covers 5 query types designed to stress-test specific failure modes:

| Type | Count | Tests for |
|---|---|---|
| `single_turn` | ~12 | Basic constraint satisfaction, OOS filtering |
| `multi_turn` | ~4 | Constraint accumulation across conversation turns |
| `edge_case` | ~4 | Missing specs, off-by-one constraints, cold-start products |
| `out_of_stock` | ~2 | Correct OOS handling when all candidates are unavailable |
| `adversarial` | ~1 | Vague descriptions that tempt fabrication |

---

## Catalog edge cases

The mock catalog deliberately includes:

| Edge case | Product | Why it matters |
|---|---|---|
| Out of stock | `of_006`, `kt_004`, `ce_005`, `ce_012` | RetrievalNode guardrail |
| Missing spec fields | `of_008` (no diameter/capacity) | ConstraintCheckNode treats as violation |
| Almost-satisfies | `of_007` (diameter=25, limit=24) | Off-by-one constraint check |
| Vague description, no spec backing | `of_008` "perfect for large umbrellas" but no `max_umbrella_size_feet` | Groundedness test |
| Cold start (near-empty specs) | `of_010`, `kt_014` | Ranking penalizes, groundedness fails |

---

## Metrics

| Metric | Description | Target |
|---|---|---|
| `top1_valid_rate` | Top result is in-stock and satisfies all hard constraints | ≥ 0.80 |
| `constraint_satisfaction_rate` | % ranked products with no hard constraint violations | ≥ 0.85 |
| `avg_groundedness` | Average LLM groundedness score across ranked products | ≥ 0.70 |
| `no_valid_results_rate` | % queries returning zero valid results | ≤ 0.10 |
| `oos_rate_top1` | % queries where top result is out of stock | ≤ 0.05 |

---

## Eval coverage gaps

This suite is intentionally scoped to offline accuracy. Known gaps:

| Gap | What it would require |
|---|---|
| Response quality beyond groundedness (helpfulness, tone, verbosity) | LLM-as-judge rubric on `final_response` |
| Spec citation accuracy (right product, wrong spec value cited) | Per-claim fact extraction + verification |
| Multi-turn constraint forgetting | Cross-turn constraint accumulation assertions |
| Query cost and latency | Token counting + wall-clock timing per node |
| Run-over-run variance (LLM non-determinism) | N=3+ repeated runs, per-metric std dev |
| Live user signal (clicks, purchases, returns) | Online eval infrastructure, attribution window |
| Semantic similarity to ideal response | Reference answers + embedding similarity |

---

## Eval philosophy

- **Missing spec ≠ satisfied constraint** — the agent must prove a claim, not assume it
- **Guardrail metrics** block response generation (stock, hard constraints, groundedness)
- **North star metrics** measure quality trends over time via Langfuse drift detection
- Eval tests run in CI; Langfuse handles production observability — two distinct roles
