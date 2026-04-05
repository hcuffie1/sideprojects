CANONICAL_QUERIES = [
    {
        "id": "q_001",
        "query": "umbrella base that can hold a 15 foot umbrella and is less than 24 inches wide",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "max_umbrella_size_feet", "op": "gte", "value": 15},
            {"field": "diameter_inches", "op": "lte", "value": 24}
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "The umbrella base query — our primary test case"
    },
    {
        "id": "q_002",
        "query": "kids building set for ages 6 and up under $50",
        "expected_category": "kids_toys",
        "hard_constraints": [
            {"field": "age_range_min", "op": "lte", "value": 6},
            {"field": "price", "op": "lte", "value": 50}
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Age + price constraint"
    },
    {
        "id": "q_003",
        "query": "wireless headphones with at least 20 hours battery life",
        "expected_category": "consumer_electronics",
        "hard_constraints": [
            {"field": "battery_life_hours", "op": "gte", "value": 20}
        ],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Battery life constraint"
    },
    {
        "id": "q_004",
        "query": "patio umbrella base",  # NO specific constraints
        "expected_category": "outdoor_furniture",
        "hard_constraints": [],
        "expected_top_result_in_stock": True,
        "expected_no_hallucination": True,
        "description": "Vague query — no constraints"
    },
    {
        "id": "q_005",
        "query": "umbrella base under 10 inches wide that holds 20 foot umbrella",
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "diameter_inches", "op": "lte", "value": 10},
            {"field": "max_umbrella_size_feet", "op": "gte", "value": 20}
        ],
        "expected_top_result_in_stock": True,
        "expected_no_products_found": True,  # impossible constraint combo
        "description": "Impossible constraints — agent should say nothing found"
    },
    {
        "id": "q_006",
        "query": "patio umbrella base that's less than 20 bucks",  # only dollar constraint
        "expected_category": "outdoor_furniture",
        "hard_constraints": [
            {"field": "price", "op": "lte", "value": 20}
        ],
        "expected_top_result_in_stock": False,
        "expected_no_hallucination": True,
        "description": "Impossible constraints given catalog"
    }
]
