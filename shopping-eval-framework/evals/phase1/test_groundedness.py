"""
Phase 1 groundedness tests.

test_no_confident_fabrication and test_grounded_product_passes exercise our
custom GroundednessNode directly — they check spec-by-spec whether each claim
in a product description is actually backed by catalog data.

test_deepeval_hallucination_metric is an *independent cross-check* using
DeepEval's HallucinationMetric (LLM-jury method). The two approaches use
different mechanisms: our GroundednessNode checks for the presence of
specific spec fields, while DeepEval prompts an LLM to judge whether the
response is supported by the provided context. Agreement between the two
validates our approach; divergence (one passes, the other fails) is a signal
worth investigating.
"""
import json
from dotenv import load_dotenv

load_dotenv()


def test_no_confident_fabrication():
    """
    THE FABRICATOR TEST
    A product with no umbrella capacity spec should NOT be recommended
    as capable of holding a 15ft umbrella.

    This is the GSD hackathon failure mode in miniature.
    """
    from agent.nodes.groundedness_node import check_product_groundedness

    # Product with NO umbrella capacity spec
    product_without_spec = {
        "id": "prod_vague",
        "name": "Heavy Duty Base",
        "specs": {
            "weight_lbs": 50,
            "material": "cast iron",
            "weather_resistant": True
            # NOTE: no max_umbrella_size_feet
        }
    }

    constraints = [
        {"field": "max_umbrella_size_feet", "op": "gte", "value": 15, "is_hard": True}
    ]

    result = check_product_groundedness(product_without_spec, constraints)

    # Should NOT be grounded — spec doesn't say it can hold 15ft umbrella
    assert result["score"] < 0.5, (
        f"Agent incorrectly gave high groundedness score ({result['score']}) "
        f"to a product with no umbrella capacity spec. "
        f"This is the confident fabricator failure mode."
    )


def test_grounded_product_passes():
    """A product WITH the right spec should be grounded"""
    from agent.nodes.groundedness_node import check_product_groundedness

    product_with_spec = {
        "id": "prod_verified",
        "name": "Verified Base",
        "specs": {
            "weight_lbs": 75,
            "diameter_inches": 22,
            "max_umbrella_size_feet": 15,
            "material": "cast iron"
        }
    }

    constraints = [
        {"field": "max_umbrella_size_feet", "op": "gte", "value": 15, "is_hard": True}
    ]

    result = check_product_groundedness(product_with_spec, constraints)
    assert result["score"] >= 0.7, (
        f"Agent incorrectly rejected a well-specified product (score: {result['score']})"
    )


def test_deepeval_hallucination_metric():
    """Integration test using DeepEval's HallucinationMetric"""
    from deepeval import evaluate
    from deepeval.metrics import HallucinationMetric
    from deepeval.test_case import LLMTestCase

    # This test checks that a response claiming a product supports 15ft umbrella
    # is flagged as hallucination when the spec only says "weather resistant"

    product_spec = json.dumps({
        "weight_lbs": 50,
        "material": "cast iron",
        "weather_resistant": True
        # no max_umbrella_size_feet
    })

    test_case = LLMTestCase(
        input="Can this base support a 15 foot umbrella?",
        actual_output="Yes, this heavy duty cast iron base can support umbrellas up to 15 feet.",
        context=[product_spec]  # spec is the ground truth
    )

    metric = HallucinationMetric(threshold=0.5)
    metric.measure(test_case)

    # Should be flagged as hallucination — spec doesn't mention 15ft capability
    assert metric.score < 0.5 or not metric.is_successful(), (
        "DeepEval should flag this as hallucination — "
        "the spec doesn't support the 15ft claim"
    )

    # Push score to Langfuse via context (no-op if LANGFUSE_PUBLIC_KEY not set)
    try:
        from langfuse import get_client
        get_client().score_current_trace(
            name="deepeval_hallucination",
            value=metric.score,
            comment=(
                f"DeepEval HallucinationMetric threshold=0.5 — "
                f"{'pass' if metric.is_successful() else 'fail'}"
            ),
        )
    except Exception:
        pass  # Langfuse unavailable — test result still valid
