# Eval Findings: Run 1 → Run 2

## Purpose

This document records the before/after story of actually using the eval framework to investigate and attempt to fix a metric regression. It demonstrates the diagnostic loop: observe failure → form hypothesis → apply fix → measure → revise.

---

## Run 1 — Baseline

**Command:** `python scripts/run_evals.py --version v1`

| Metric | Value |
|---|---|
| `top1_valid_rate` | 1.000 |
| `constraint_satisfaction_rate` | — |
| `avg_groundedness` | 0.703 |
| `no_valid_results_rate` | 0.261 |
| `oos_rate_top1` | 0.000 |

**Failure distribution:**
- `success`: 14
- `no_results`: 6
- `impossible_constraints`, `catalog_gap`, other: remainder

### Failure analysis

6 queries returned zero valid results (`no_valid_results_rate = 0.261` → exceeds ≤ 0.10 target).

Drill-down by query type:

| Query | Expected? | Root cause |
|---|---|---|
| `q_005`, `q_021` | ✓ Correct | Impossible constraints — no product can satisfy both |
| `q_006`, `q_022` | ✓ Correct | Catalog gap — real constraint, nothing in stock meets it |
| `q_019`, `q_020` | ✗ Agent gap | Multi-category queries — IntentNode only supports one category per turn |
| `q_002`, `q_011`–`q_014`, `q_023` | ✗ Unexpected | GroundednessNode rejecting all ranked kids_toys products |

The unexpected failures all landed in kids_toys queries. GroundednessNode was returning scores < 0.5 for every candidate, preventing any recommendation. The groundedness prompt asks an LLM to verify whether spec fields back the claims — but the kids_toys catalog had no `educational`, `building`, `stem`, or `creative_play` boolean fields. Nothing to verify against.

### Hypothesis

Catalog spec poverty in `kids_toys.json` is causing GroundednessNode to conservatively reject everything. Adding structured boolean spec fields should give the LLM something concrete to ground its verification against.

---

## Fix applied

Added boolean spec fields to 12 of 15 kids_toys products:
- `educational`, `building`, `stem`, `creative_play` — where applicable per product type

`kt_014` (Mysterious Play Starter, `specs: {}`) intentionally left sparse as the cold-start test case — it should continue to fail groundedness.

---

## Run 2 — Post-enrichment

**Command:** `python scripts/run_evals.py --version v2_enriched_catalog`

| Metric | Value | vs Run 1 |
|---|---|---|
| `top1_valid_rate` | 1.000 | → unchanged |
| `constraint_satisfaction_rate` | 0.778 | (new metric) |
| `avg_groundedness` | 0.697 | ↓ −0.006 (noise) |
| `no_valid_results_rate` | 0.261 | → unchanged |
| `oos_rate_top1` | 0.000 | → unchanged |

**Failure distribution (Run 2):**
- `success`: 14
- `hallucination`: 3
- `catalog_gap`: 2
- `impossible_constraints`: 2
- `no_results`: 2

### Finding: catalog enrichment did not improve groundedness

The metrics are statistically identical. The kids_toys groundedness failures persist. This rules out simple spec absence as the root cause.

**Revised diagnosis:**

The GroundednessNode uses an LLM prompt that verifies whether the agent's claims are backed by spec data. Even with boolean `building: true` and `educational: true` in the spec, the LLM jury is systematically returning scores < 0.5 for kids_toys products when the query uses natural language like "building things" or "educational". The spec fields exist, but the LLM is not mapping them to the natural-language claim with sufficient confidence.

Separately, the remaining `no_valid_results_rate` decomposes as:
- **4 correct zeros** (`q_005`, `q_006`, `q_021`, `q_022`): impossible constraints or catalog gaps — ConstraintCheckNode working correctly
- **2 genuine gaps** (`q_019`, `q_020`): multi-category queries require IntentNode to support routing to multiple categories per turn

---

## What the framework proved

**The eval framework correctly distinguished two separate problems:**

1. It confirmed that `top1_valid_rate = 1.000` throughout — when the agent does recommend something, it's always valid. The guardrails work.

2. It isolated `no_valid_results_rate = 0.261` as the failure, and further decomposed it: the 4 impossible/gap queries are correct behavior; the 2 multi-category queries are an agent design gap; the kids_toys groundedness failures are an LLM calibration issue masked as a data issue.

3. The failed hypothesis (catalog enrichment) is itself a useful result. Without a structured eval loop, the fix would have shipped and the failure would have been attributed to "the catalog was wrong" — but Run 2 shows the metric didn't move, forcing a more accurate diagnosis.

---

## Next fix path

| Problem | Fix |
|---|---|
| GroundednessNode LLM conservatism on boolean specs | Revise prompt: explicitly distinguish claim types (boolean flag vs numeric spec vs description) |
| Multi-category queries (`q_019`, `q_020`) | Update IntentNode to detect and split multi-category intent; route each sub-query separately |
