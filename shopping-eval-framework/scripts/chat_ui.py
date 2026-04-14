"""
Streamlit chat UI for the shopping agent.

Visual demo layer on top of agent/graph.py. Does not modify the agent.

Features:
  - New User / Returning User session toggle
  - Returning user: collapsible memory context panel shows preferences and
    recent purchases BEFORE the user types — makes long-horizon memory tangible
  - Product cards in response with ⚠️ badge if output_violations > 0 or
    avg_groundedness < 0.7
  - Per-query footer: latency, tokens, estimated cost

Run:
    streamlit run scripts/chat_ui.py
"""
import sys
import os
import time
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from agent.graph import agent
from agent.memory import MemoryManager
from evals.pricing import cost_for_tokens

try:
    from langfuse import observe as _lf_observe, get_client as _lf_get_client
    _LANGFUSE_ENABLED = True
except Exception:
    _LANGFUSE_ENABLED = False


@(_lf_observe(name="chat-turn") if _LANGFUSE_ENABLED else lambda f: f)
def _invoke_agent(state: dict, query: str, user_id: str | None) -> dict:
    if _LANGFUSE_ENABLED:
        try:
            _lf_get_client().update_current_trace(
                name=f"chat: {query[:60]}",
                user_id=user_id or "anonymous",
                tags=["chat_ui"],
                metadata={"source": "streamlit"},
            )
        except Exception:
            pass
    return agent.invoke(state)

EMPTY_STATE = {
    "conversation_history": [],
    "query": "",
    "parsed_constraints": [],
    "category": None,
    "candidate_products": [],
    "filtered_products": [],
    "constraint_violations": [],
    "ranked_products": [],
    "groundedness_annotations": [],
    "final_response": "",
    "agent_rationale": "",
    "trace_id": None,
    "eval_scores": None,
    "_token_usage": None,
    "user_id": None,
}

_DEMO_USERS = {
    "Alex (user_001)": "user_001",
    "Jordan (user_002)": "user_002",
}


# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Shopping Agent",
    page_icon="🛍️",
    layout="wide",
)


# ── Session state ──────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_state" not in st.session_state:
    st.session_state.agent_state = {**EMPTY_STATE}


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Session")
    user_mode = st.selectbox("User type", ["New User", "Returning User"])

    user_id = None
    if user_mode == "Returning User":
        display_name = st.selectbox("Select user", list(_DEMO_USERS.keys()))
        user_id = _DEMO_USERS[display_name]

        # Memory context panel — shown before the user types
        mm = MemoryManager()
        ctx = mm.get_user_context(user_id)
        with st.expander("Memory Context (loaded before query)", expanded=True):
            if ctx:
                st.markdown(f"**{ctx.get('name', user_id)}**")
                prefs = ctx.get("preferences", {})
                if prefs:
                    st.markdown("**Preferences:**")
                    for k, v in prefs.items():
                        badge = "🔵" if v["memory_type"] == "explicit" else "⚪"
                        st.markdown(
                            f"- {badge} `{k}` = {v['value']} "
                            f"*(conf: {v['confidence']:.0%})*"
                        )
                purchases = ctx.get("purchases", [])
                if purchases:
                    st.markdown("**Recent purchases:**")
                    for p in purchases:
                        occasion = f" — {p['occasion']}" if p['occasion'] else ""
                        st.markdown(
                            f"- {p['product_name']} [{p['category']}]{occasion}"
                        )
                avoid = ctx.get("avoid_ids", [])
                if avoid:
                    st.caption(f"Will not re-recommend: {', '.join(avoid)}")
            else:
                st.caption("No memory found for this user.")
    else:
        st.caption("No memory loaded — fresh session.")

    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.session_state.agent_state = {**EMPTY_STATE}
        st.rerun()


# ── Main ───────────────────────────────────────────────────────────────────────

st.title("Shopping Agent")
st.caption("Powered by LangGraph + Gemini 2.5 Flash")

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("footer"):
            st.caption(msg["footer"])

# Input
prompt = st.chat_input("What are you looking for?")

if prompt:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            state = {
                **st.session_state.agent_state,
                "query": prompt,
                "user_id": user_id,
            }

            t0 = time.perf_counter()
            result = _invoke_agent(state, prompt, user_id)
            latency_ms = (time.perf_counter() - t0) * 1000

        # Update persistent state (carries conversation_history forward)
        st.session_state.agent_state = {**result, "user_id": user_id}

        # ── Response text ──────────────────────────────────────────────────────
        final_response = result.get("final_response", "")
        st.markdown(final_response)

        # ── Product cards ──────────────────────────────────────────────────────
        ranked = result.get("ranked_products", [])
        annotations = {
            a["product_id"]: a.get("score", 1.0)
            for a in result.get("groundedness_annotations", [])
            if "product_id" in a
        }
        violations = result.get("constraint_violations", [])
        output_violations = len([
            v for v in violations
            if v.get("is_hard", True)
        ])
        avg_groundedness = (
            sum(annotations.values()) / len(annotations) if annotations else 1.0
        )
        needs_warning = output_violations > 0 or avg_groundedness < 0.7

        if ranked:
            st.markdown("---")
            cols = st.columns(min(len(ranked), 3))
            for i, product in enumerate(ranked[:3]):
                with cols[i]:
                    pid = product.get("id", "")
                    g_score = annotations.get(pid, 1.0)
                    card_warning = g_score < 0.7 or output_violations > 0
                    badge = "⚠️ " if card_warning else ""
                    st.markdown(
                        f"**{badge}{product.get('name', pid)}**"
                    )
                    price = product.get("price")
                    if price:
                        st.markdown(f"${price:,.2f}")
                    category = product.get("category", "")
                    if category:
                        st.caption(category)
                    st.caption(f"Groundedness: {g_score:.0%}")

        # ── Footer ─────────────────────────────────────────────────────────────
        token_usage = result.get("_token_usage") or {}
        in_tok = token_usage.get("input_total", 0)
        out_tok = token_usage.get("output_total", 0)
        total_tok = in_tok + out_tok
        cost = cost_for_tokens(in_tok, out_tok)

        footer_parts = [f"{latency_ms:.0f}ms"]
        if total_tok > 0:
            footer_parts.append(f"{total_tok:,} tokens")
            footer_parts.append(f"~${cost:.4f}")
        if _LANGFUSE_ENABLED:
            try:
                tid = _lf_get_client().get_current_trace_id()
                if tid:
                    footer_parts.append(f"trace `{tid[:8]}`")
            except Exception:
                pass
        footer = "  |  ".join(footer_parts)
        if needs_warning:
            footer += "  |  ⚠️ low confidence result"
        st.caption(footer)

        # Store message for history
        st.session_state.messages.append({
            "role": "assistant",
            "content": final_response,
            "footer": footer,
        })
