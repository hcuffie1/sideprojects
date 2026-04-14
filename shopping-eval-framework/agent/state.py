from typing import TypedDict, List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class Constraint:
    field: str
    op: str  # "lte", "gte", "eq", "contains"
    value: Any
    is_hard: bool  # hard constraints must be satisfied; soft are preferences


class AgentState(TypedDict):
    # Input
    query: str
    conversation_history: List[Dict]

    # IntentNode output
    parsed_constraints: List[Dict]
    category: Optional[str]

    # RetrievalNode output
    candidate_products: List[Dict]

    # ConstraintCheckNode output
    filtered_products: List[Dict]
    constraint_violations: List[Dict]  # {product_id, violated_constraint, actual, required}

    # RankingNode output
    ranked_products: List[Dict]  # top 5

    # GroundednessNode output
    groundedness_annotations: List[Dict]  # {product_id, score, flagged_claims}

    # ResponseNode output
    final_response: str
    agent_rationale: str  # the "Wizard says" equivalent

    # Eval metadata (populated by eval framework, not agent)
    trace_id: Optional[str]
    eval_scores: Optional[Dict]

    # Token usage accumulated across all LLM nodes {input_total, output_total}
    _token_usage: Optional[Dict]

    # Optional user ID for memory-aware sessions (wired in by chat UI or caller)
    user_id: Optional[str]
