"""
Langfuse v4 tracing shim for LangGraph nodes.

Wraps langfuse.observe so node files need no direct langfuse import.
When LANGFUSE_PUBLIC_KEY is not set, @observe() is a transparent no-op.

Usage (unchanged from v2/v3):
    from agent.tracing import traced_node

    @traced_node("IntentNode")
    def intent_node(state: dict) -> dict:
        ...
"""
from langfuse import observe as _observe


def traced_node(node_name: str):
    """Return a Langfuse @observe() span decorator with the given node name."""
    return _observe(name=node_name)
