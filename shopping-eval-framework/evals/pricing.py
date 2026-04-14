"""
Token pricing constants for Gemini 2.5 Flash.

Usage:
    from evals.pricing import cost_for_tokens
    cost = cost_for_tokens(input_tokens=1200, output_tokens=300)
"""

# Gemini 2.5 Flash pricing (per 1M tokens, as of May 2025)
INPUT_COST_PER_1M = 0.10
OUTPUT_COST_PER_1M = 0.40


def cost_for_tokens(input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a given token usage."""
    return (
        input_tokens / 1_000_000 * INPUT_COST_PER_1M
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_1M
    )
