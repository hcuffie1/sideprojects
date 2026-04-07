"""
Langfuse API client for querying historical data (drift detection).

Instrumentation (traces, spans, scores) is handled automatically by the
@observe() decorator in langfuse.decorators — no client needed for that.

This module exists solely to provide a client for drift_detector.py to query
historical score data via the Langfuse REST API.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def get_langfuse_api_client():
    """
    Return a Langfuse client for API queries, or None if not configured.
    Only needed for drift detection — not for instrumentation.
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse import Langfuse
        return Langfuse()
    except Exception as e:
        print(f"[langfuse] API client init failed: {e}")
        return None
