"""Acme pipeline assistant.

Two columns. Chat on the left. On the right, four stacked sections, all
visible without clicking: the computed figures, the flags, the source rows
with their filter and row count, and a trace of the intent and the answering
snapshot. The restatement renders inside the answer itself, not in the trace,
because it is the only backstop against a silent misroute.
"""

from __future__ import annotations

import streamlit as st

from acme.domain import Answered, Refused
from acme.loading import load_data
from acme.pipeline import ask

st.set_page_config(page_title="Acme pipeline assistant", layout="wide")


@st.cache_resource
def get_data():
    return load_data()


data = get_data()

if "history" not in st.session_state:
    st.session_state.history = []  # list of (question, Answer)

chat_col, panel_col = st.columns([3, 2])

with chat_col:
    st.title("Acme pipeline assistant")
    st.caption(f"As of {data.as_of}. No question here reaches a language model in this build.")

    for question, answer in st.session_state.history:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            if isinstance(answer, Refused):
                st.warning(f"I can't answer that: {answer.reason}")
                st.caption(answer.hint)
            else:
                if answer.router_mode == "offline":
                    st.caption("Routed offline — the keyword router answered this one.")
                st.write(answer.prose)

    question = st.chat_input("Ask about pipeline, e.g. \"how are we tracking this quarter\"")
    if question:
        answer = ask(question, data)
        st.session_state.history.append((question, answer))
        st.rerun()

with panel_col:
    st.subheader("Details")
    latest = st.session_state.history[-1][1] if st.session_state.history else None

    if latest is None:
        st.info("Ask a question to see the figures, flags, source rows, and trace here.")
    elif isinstance(latest, Refused):
        st.markdown("### Refused")
        st.write(latest.reason)
        st.markdown("### Coverage")
        st.write(latest.hint)
        if latest.intent is not None:
            st.markdown("### Trace")
            st.json(latest.intent.model_dump())
    else:
        answer: Answered = latest

        st.markdown("### Figures")
        for fact in answer.facts.values():
            st.metric(fact.label, fact.formatted())

        st.markdown("### Flags")
        for flag in answer.flags:
            st.markdown(f"**{flag.title}**")
            st.caption(flag.detail)

        st.markdown("### Source rows")
        st.caption(f"{answer.row_count} rows, snapshot: {answer.snapshot}")
        for key, value in answer.filters.items():
            st.caption(f"{key}: {value}")
        st.dataframe(answer.source_rows, use_container_width=True, hide_index=True)

        st.markdown("### Trace")
        st.caption(f"Router: {answer.router_mode}")
        st.caption(f"Snapshot answering: {answer.snapshot}")
        if answer.intent is not None:
            st.json(answer.intent.model_dump())

with st.sidebar:
    st.markdown("### What I can answer")
    from acme.catalog import build_catalog

    catalog = build_catalog(data)
    for spec in catalog.metrics:
        st.markdown(f"**{spec.name}** — {', '.join(spec.groupings)}")
        st.caption(spec.description)
        for example in spec.examples:
            st.caption(f"e.g. “{example}”")
