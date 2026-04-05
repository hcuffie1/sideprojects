# Shopping Agent Eval Framework

A multi-turn shopping agent evaluation framework built with LangGraph. Demonstrates evaluation concepts used at Wizard-style conversational AI companies — specifically catching the **confident fabricator** failure mode.

## What it does

A 6-node LangGraph agent processes shopping queries through:

1. **IntentNode** — extracts structured constraints (hard/soft) from natural language
2. **RetrievalNode** — loads catalog, filters in-stock products only
3. **ConstraintCheckNode** — rule-based filtering; treats missing spec fields as violations
4. **RankingNode** — scores by spec completeness + soft constraint satisfaction
5. **GroundednessNode** — asks LLM whether specs can actually verify each claim
6. **ResponseNode** — only recommends products that passed groundedness (score > 0.5)

## The key test

```bash
pytest evals/phase1/test_groundedness.py::test_no_confident_fabrication -v
```

This test catches the **confident fabricator** failure mode: an agent claiming a product can hold a 15-foot umbrella when the spec data contains no umbrella capacity field. The agent must score this < 0.5 (not grounded). This mirrors the failure seen in production shopping agents that hallucinate product capabilities not present in spec data.

## Setup

```bash
pip install -r requirements.txt
```

Add your keys to `.env`:
```
OPENAI_API_KEY=your_key_here
LANGSMITH_API_KEY=your_key_here   # optional, for LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=shopping-eval-framework
```

## Running

```bash
# The fabricator test (most important)
pytest evals/phase1/test_groundedness.py::test_no_confident_fabrication -v

# Logic-only tests (no API key needed)
pytest evals/phase1/test_constraint_checking.py evals/phase1/test_retrieval.py evals/phase1/test_ranking.py -v

# Full Phase 1 test suite
pytest evals/phase1/ -v

# End-to-end on all canonical queries
python scripts/run_evals.py

# Run a specific canonical query
python scripts/run_evals.py q_001
```

## Catalog edge cases

The mock catalog deliberately includes:

| Edge case | Product | Why it matters |
|---|---|---|
| Out of stock | `of_006`, `kt_004`, `ce_005`, `ce_012` | RetrievalNode guardrail |
| Missing spec fields | `of_008` (no diameter/capacity) | ConstraintCheckNode treats as violation |
| Almost-satisfies | `of_007` (diameter=25, limit=24) | Off-by-one constraint check |
| Vague description, no spec backing | `of_008` says "perfect for large umbrellas" but no `max_umbrella_size_feet` | Groundedness test |
| Cold start (near-empty specs) | `of_010`, `kt_014` | Ranking penalizes, groundedness fails |

## Evaluation philosophy

- **Guardrail metrics** (must pass before response is generated): stock availability, hard constraint satisfaction, groundedness score > 0.5
- **North star metrics** (measure quality): response accuracy, constraint coverage
- Missing spec ≠ satisfied constraint — the agent must prove a claim, not assume it
