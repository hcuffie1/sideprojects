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
    Return a LangfuseAPI client for querying historical data, or None if not
    configured. Only needed for drift detection — not for instrumentation.

    Uses LangfuseAPI (the REST query client) rather than Langfuse() (the
    instrumentation client). In v4 these are separate objects.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None
    try:
        from langfuse.api import LangfuseAPI
        return LangfuseAPI(
            base_url=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            username=public_key,
            password=secret_key,
        )
    except Exception as e:
        print(f"[langfuse] API client init failed: {e}")
        return None
