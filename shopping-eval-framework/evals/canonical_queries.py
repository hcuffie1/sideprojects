"""
Canonical query set for the shopping agent eval framework.

Query types:
  search       — clear constraint extraction and retrieval
  compare      — ranking + explanation fidelity
  substitute   — multi-turn: "out of stock / too expensive, what else?"
  gift         — ambiguous intent, soft constraints
  bundle       — multi-item / multi-category requests
  catalog_gap  — valid constraints but nothing in catalog satisfies them
                 (satisfiable=True) or physically impossible (satisfiable=False)
  multi_turn   — context retention across turns

The `satisfiable` field on catalog_gap queries drives the failure taxonomy split:
  satisfiable=False → failure_mode = "impossible_constraints"
  satisfiable=True  → failure_mode = "catalog_gap"
"""

CANONICAL_QUERIES = [

    # ── SEARCH ────────────────────────────────────────────────────────────────

    {
        "id": "q_001",
        "query_type": "search",
        "query": "umbrella base that can hold a 15 foot umbrella and is less than 24 inches wide",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "max_umbrella_size_feet", "op": "gte", "value": 15},
            {"field": "diameter_inches", "op": "lte", "value": 24},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Primary umbrella base query — two hard constraints",
    },
    {
        "id": "q_002",
        "query_type": "search",
        "query": "kids building set for ages 6 and up under $50",
        "expected_category": "kids_toys",
        "hard_constraints": [
            {"field": "age_range_min", "op": "lte", "value": 6},
            {"field": "price", "op": "lte", "value": 50},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Age + price constraint",
    },
    {
        "id": "q_003",
        "query_type": "search",
        "query": "wireless headphones with at least 20 hours battery life",
        "expected_category": "consumer_electronics",
        "hard_constraints": [
            {"field": "battery_life_hours", "op": "gte", "value": 20},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Single spec constraint — battery life",
    },
    {
        "id": "q_004",
        "query_type": "search",
        "query": "patio umbrella base",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Vague search — no explicit constraints, tests retrieval alone",
    },
    {
        "id": "q_009",
        "query_type": "search",
        "query": "patio umbrella base that weighs at least 50 pounds",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "weight_lbs", "op": "gte", "value": 50},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Weight constraint — heavier base for wind stability",
    },
    {
        "id": "q_010",
        "query_type": "search",
        "query": "bluetooth speaker with at least 10 hours of battery life",
        "expected_category": "consumer_electronics",
        "hard_constraints": [
            {"field": "battery_life_hours", "op": "gte", "value": 10},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Electronics search — speaker battery life constraint",
    },
    {
        "id": "q_011",
        "query_type": "search",
        "query": "kids creative play set for ages 4 and up under $60",
        "expected_category": "kids_toys",
        "hard_constraints": [
            {"field": "age_range_min", "op": "lte", "value": 4},
            {"field": "price", "op": "lte", "value": 60},
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Kids toy — younger age range + price constraint",
    },

    # ── GIFT ──────────────────────────────────────────────────────────────────

    {
        "id": "q_012",
        "query_type": "gift",
        "query": "birthday gift for my 7-year-old nephew who loves building things, around $40",
        "expected_category": "kids_toys",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Gift — soft age + soft price, building interest",
    },
    {
        "id": "q_013",
        "query_type": "gift",
        "query": "looking for a gift for someone who spends a lot of time on their patio, budget around $100",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Gift — outdoor category, soft budget constraint",
    },
    {
        "id": "q_014",
        "query_type": "gift",
        "query": "fun educational toy for a 5-year-old, under $35",
        "expected_category": "kids_toys",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Gift — young child, educational soft constraint",
    },

    # ── COMPARE ───────────────────────────────────────────────────────────────

    {
        "id": "q_015",
        "query_type": "compare",
        "query": "which wireless headphones have the best battery life? show me a few options",
        "expected_category": "consumer_electronics",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Compare — ranking by single spec, tests explanation fidelity",
    },
    {
        "id": "q_016",
        "query_type": "compare",
        "query": "show me the most heavy-duty umbrella bases you carry and explain the differences",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Compare — multiple results, spec-grounded explanation test",
    },

    # ── SUBSTITUTE (multi-turn: refine after seeing first results) ────────────

    {
        "id": "q_017",
        "query_type": "substitute",
        "type": "multi_turn",
        "turns": [
            {
                "query": "show me wireless headphones",
                "expected_category": "consumer_electronics",
            },
            {
                "query": "those are too expensive, do you have something under $80?",
                "hard_constraints": [
                    {"field": "price", "op": "lte", "value": 80}
                ],
            },
        ],
        "description": "Substitute — too expensive, refine to cheaper option",
    },
    {
        "id": "q_018",
        "query_type": "substitute",
        "type": "multi_turn",
        "turns": [
            {
                "query": "I need an umbrella base that can hold an 11-foot umbrella",
                "expected_category": "outdoor_furniture",
            },
            {
                "query": "the first result looks too heavy, I need something under 40 pounds",
                "hard_constraints": [
                    {"field": "weight_lbs", "op": "lte", "value": 40}
                ],
            },
        ],
        "description": "Substitute — too heavy, add weight upper bound constraint",
    },

    # ── BUNDLE ────────────────────────────────────────────────────────────────

    {
        "id": "q_019",
        "query_type": "bundle",
        "query": "I'm setting up a patio — need a heavy umbrella base and also a toy my kid can play with outside",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Bundle — two categories, tests multi-intent handling",
    },
    {
        "id": "q_020",
        "query_type": "bundle",
        "query": "road trip — need something to keep a 6-year-old entertained and wireless headphones for the adults",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Bundle — kids toy + electronics, cross-category request",
    },

    # ── CATALOG GAP ───────────────────────────────────────────────────────────

    {
        "id": "q_005",
        "query_type": "catalog_gap",
        "satisfiable": False,
        "query": "umbrella base under 10 inches wide that holds a 20-foot umbrella",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "diameter_inches", "op": "lte", "value": 10},
            {"field": "max_umbrella_size_feet", "op": "gte", "value": 20},
        ],
        "expected_no_products_found": True,
        "description": "Impossible — contradictory constraints (tiny base, huge umbrella)",
    },
    {
        "id": "q_006",
        "query_type": "catalog_gap",
        "satisfiable": True,
        "query": "patio umbrella base that's less than 20 bucks",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "price", "op": "lte", "value": 20},
        ],
        "expected_no_products_found": True,
        "description": "Catalog gap — valid price constraint, nothing in catalog that cheap",
    },
    {
        "id": "q_021",
        "query_type": "catalog_gap",
        "satisfiable": False,
        "query": "umbrella base that weighs under 3 pounds and can hold a 20-foot umbrella",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "weight_lbs", "op": "lte", "value": 3},
            {"field": "max_umbrella_size_feet", "op": "gte", "value": 20},
        ],
        "expected_no_products_found": True,
        "description": "Impossible — ultra-light base with massive umbrella capacity",
    },
    {
        "id": "q_022",
        "query_type": "catalog_gap",
        "satisfiable": True,
        "query": "wireless headphones with at least 80 hours battery life",
        "expected_category": "consumer_electronics",
        "hard_constraints": [
            {"field": "battery_life_hours", "op": "gte", "value": 80},
        ],
        "expected_no_products_found": True,
        "description": "Catalog gap — valid spec, nothing in catalog meets 80hr threshold",
    },

    # ── MULTI-TURN ────────────────────────────────────────────────────────────

    {
        "id": "q_007",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "I'm looking for an umbrella base",
                "expected_category": "outdoor_furniture",
            },
            {
                "query": "it needs to hold a 15 foot umbrella",
            },
            {
                "query": "and it has to be under 24 inches wide",
                "expected_no_products_found": False,
            },
        ],
        "description": "Multi-turn refinement — category T1, constraints T2+T3",
    },
    {
        "id": "q_008",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "show me wireless headphones",
                "expected_category": "consumer_electronics",
            },
            {
                "query": "actually I need at least 30 hours battery life",
                "hard_constraints": [
                    {"field": "battery_life_hours", "op": "gte", "value": 30}
                ],
            },
        ],
        "description": "Multi-turn headphones — constraint refinement across turns",
    },
    {
        "id": "q_023",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "I need something for my kid",
                "expected_category": "kids_toys",
            },
            {
                "query": "she's 6 years old",
            },
            {
                "query": "and it should be educational, under $50",
                "hard_constraints": [
                    {"field": "price", "op": "lte", "value": 50}
                ],
            },
        ],
        "description": "Multi-turn — category implied T1, age refinement T2, price+feature T3",
    },

    # ── CONSTRAINT UPDATE / EDGE CASES ────────────────────────────────────────

    {
        "id": "q_024",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "Show me outdoor umbrella bases that can hold a 15-foot umbrella",
                "expected_category": "outdoor_furniture",
                "hard_constraints": [
                    {"field": "max_umbrella_size_feet", "op": "gte", "value": 15},
                ],
            },
            {
                "query": "I also need one that's under 50 pounds",
                "hard_constraints": [
                    {"field": "max_umbrella_size_feet", "op": "gte", "value": 15},
                    {"field": "weight_lbs", "op": "lte", "value": 50},
                ],
            },
            {
                "query": "Hmm, actually I need it under 30 pounds",
                "hard_constraints": [
                    {"field": "max_umbrella_size_feet", "op": "gte", "value": 15},
                    {"field": "weight_lbs", "op": "lte", "value": 30},
                ],
            },
        ],
        "description": "Constraint update — weight constraint superseded across turns (≤50 → ≤30)",
    },
    {
        "id": "q_025",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "I need wireless headphones with at least 30 hours of battery",
                "expected_category": "consumer_electronics",
                "hard_constraints": [
                    {"field": "battery_life_hours", "op": "gte", "value": 30},
                ],
            },
            {
                "query": "My budget is under $100",
                "hard_constraints": [
                    {"field": "battery_life_hours", "op": "gte", "value": 30},
                    {"field": "price", "op": "lte", "value": 100},
                ],
            },
            {
                "query": "Wait, I actually need at least 40 hours battery life",
                "hard_constraints": [
                    {"field": "battery_life_hours", "op": "gte", "value": 40},
                    {"field": "price", "op": "lte", "value": 100},
                ],
            },
        ],
        "description": "Constraint tightening — battery minimum raised mid-conversation (≥30 → ≥40)",
    },
    {
        "id": "q_026",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "turns": [
            {
                "query": "Find me a patio umbrella base under $200",
                "expected_category": "outdoor_furniture",
                "hard_constraints": [
                    {"field": "price", "op": "lte", "value": 200},
                ],
            },
            {
                "query": "Actually forget that — I need wireless headphones instead, under $150",
                "expected_category": "consumer_electronics",
                "hard_constraints": [
                    {"field": "price", "op": "lte", "value": 150},
                ],
            },
        ],
        "description": "Cross-category pivot — user abandons category mid-conversation",
    },
    {
        "id": "q_027",
        "query_type": "multi_turn",
        "type": "multi_turn",
        "expected_no_products_found": True,
        "satisfiable": True,
        "turns": [
            {
                "query": "I'm shopping for a gift — any good kids toys under $40?",
                "expected_category": "kids_toys",
                "hard_constraints": [
                    {"field": "price", "op": "lte", "value": 40},
                ],
            },
            {
                "query": "Also I need outdoor furniture — a patio umbrella base that fits an 11-foot umbrella",
            },
        ],
        "description": "Cross-category additive — multi-intent turn; tests single-category agent limit",
    },
]
