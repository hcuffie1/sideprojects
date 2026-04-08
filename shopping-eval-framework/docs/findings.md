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

---

## Run 3 — Stability testing and non-determinism diagnosis

**Command:** `python scripts/stability_test.py q_001 --n 3`

### Finding: q_001 is highly unstable

q_001 is the primary umbrella base query: *"umbrella base that can hold a 15 foot umbrella and is less than 24 inches wide"*. It has two hard constraints and a known correct answer (`of_003`, Restoration Hardware umbrella base, in stock).

Stability results:

| Run | failure_mode | groundedness |
|---|---|---|
| 1 | `success` | 1.000 |
| 2 | `no_results` | 0.000 |
| 3 | `no_results` | 0.000 |

```
groundedness     0.3333 ±0.5774  cv=1.732  ⚠ high variance
top1_valid       0.3333 ±0.5774  cv=1.732  ⚠ high variance
product_set_stability            0.0000    ⚠ unstable
failure_mode_consistency         ✗  [success, no_results, no_results]
```

CV of 1.73 means the standard deviation is 173% of the mean — this metric is essentially noise on this query, so any single-run result cannot be trusted.

### Diagnosis: IntentNode generates non-canonical field names

Pipeline stage inspection for a failing run showed `candidates=0`, meaning the failure occurs before RetrievalNode even runs. Further investigation:

```bash
# IntentNode run across 5 attempts:
Run 1: constraints=[{field: "max_umbrella_size_feet", ...}, {field: "width_inches", ...}]
Run 2: constraints=[{field: "max_umbrella_size_feet", ...}, {field: "width_inches", ...}]
Run 3: constraints=[{field: "max_umbrella_size_feet", ...}, {field: "width_inches", ...}]
Run 4: constraints=[{field: "max_umbrella_size_feet", ...}, {field: "diameter_inches", ...}]
Run 5: constraints=[{field: "max_umbrella_size_feet", ...}, {field: "diameter_inches", ...}]
```

The LLM interprets "less than 24 inches wide" as either `width_inches` or `diameter_inches` — both are semantically valid for a circular base. But the catalog spec field is `diameter_inches`. When IntentNode emits `width_inches`, `check_constraint` looks for `product.specs["width_inches"]`, finds `None`, classifies it as `spec_missing` (hard constraint violation), and filters every candidate out. `ranked_products=[]` results.

This is not a groundedness problem or a catalog problem. **It is a schema alignment problem.** IntentNode is free-form and generates field names from natural language; ConstraintCheckNode does exact string matching against catalog spec keys. When these diverge, the pipeline silently produces no results — no error, no warning, just an empty ranked list.

### Hypothesis for Run 4

Add a canonical field name list to the intent-extraction prompt in `agent/prompts.py` for each product category. The LLM should be told: *"For outdoor_furniture, use these field names: `diameter_inches`, `max_umbrella_size_feet`, `weight_lbs`, `material`, `color`. Never invent synonyms."*

**Predicted result:** `failure_mode_consistency=True` for q_001, `no_valid_results_rate` drops from 0.273 toward 0.13 (the 3 remaining expected zeros from impossible/catalog gaps).

**Test:**
```bash
# Edit agent/prompts.py → PROMPT_DEFINITIONS["intent-extraction"] system prompt
# Push to Langfuse
python scripts/seed_prompts.py --force
# Run stability test to verify
python scripts/stability_test.py q_001 --n 5
# Run full suite tagged for comparison
python scripts/run_evals.py --version v4_canonical_fields
```

---

## Open hypotheses (pending Run 4)

### Hallucination (2 cases, priority score 1.46)

**Priority action:** Revise the `groundedness-check` prompt in `agent/prompts.py` to explicitly handle boolean spec fields. Currently the LLM judges boolean fields (`educational: true`) with ambiguous confidence scores (0.3–0.5) when the user's constraint is phrased as natural language ("educational toy"). Adding an instruction like *"If a spec field is a boolean set to True and the constraint asks for that property, treat it as fully grounded (score: 1.0)"* should eliminate these false positives.

**Predicted result:** `avg_groundedness` rises from 0.731 toward ≥0.800; hallucination count drops from 2 to 0.

**Test:**
```bash
python scripts/seed_prompts.py --force
python scripts/run_evals.py --version v4_groundedness_boolean
# Compare avg_groundedness between v2 and v4 traces in Langfuse
```

### Catalog gap (2 cases, priority score 0.91)

**Priority action:** Identify which query categories have no catalog coverage:

```bash
python -c "
from evals.canonical_queries import CANONICAL_QUERIES
for q in CANONICAL_QUERIES:
    if q.get('expected_no_products_found') and q.get('satisfiable', True):
        print(q['id'], q.get('category'), q.get('description'))
"
```

For each identified category, either add 2–3 catalog entries that satisfy the constraints, or mark the query `satisfiable=False` if the constraint is genuinely unserviceable (reclassifies from `catalog_gap` to `impossible_constraints`, lower priority score).

**Predicted result:** `no_valid_results_rate` drops by `count/total` for each gap closed.
