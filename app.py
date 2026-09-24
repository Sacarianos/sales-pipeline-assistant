"""Acme pipeline assistant.

Two even columns. Chat on the left, inside a fixed-height transcript so it
reads as a chat window rather than a page that grows forever. On the right,
the four stacked sections the spec calls for, all visible without clicking:
the computed figures, the flags, the source rows with their filter and row
count, and a trace of the intent and the answering snapshot. The restatement
renders inside the answer itself and not in the trace, because it is the only
backstop against a silent misroute.

The figures section leads with a chart so an answer has a shape before it has
a column of numbers, and the flags section separates the caveats specific to
this answer from the static definitions it rests on. Both stay on screen.
Density here is handled with typography and never by putting something behind
a click: an assumption nobody can see is the exact surprise the panel exists
to prevent.
"""

from __future__ import annotations

import html
import re
import time
from typing import Iterator

import anthropic
import streamlit as st

from acme import config
from acme.catalog import build_catalog
from acme.conversation import remember, turn
from acme.charts import chart_for
from acme.domain import Answer, Answered, Flag, Refused
from acme.query_log import QueryLog
from acme.loading import load_data
from acme.pipeline import ask

st.set_page_config(page_title="Acme pipeline assistant", layout="wide")

WORD_DELAY_SECONDS = 0.02
TRANSCRIPT_HEIGHT = 520

# The one place in this app where alarm is the correct register. Everywhere
# else the interface keeps caveats legible without making them frightening,
# because a leader alarmed by a partial-period notice stops reading notices
# altogether. The risk here is specific and real, since a model chose the
# query, so the treatment matches it. The arithmetic is computed and checked
# exactly as a metric's is. What nobody has checked is whether the query
# asks what the reader meant, and the warning says exactly that.
EXPLORATORY_WARNING = (
    "This answer didn't come from a defined metric in the catalog. A model "
    "chose the query below to answer your question. The figures were "
    "computed by pandas and the wording of the answer was checked against "
    "them, the same as a metric's. Nobody has checked that the query asks "
    "what you meant. Read it before you repeat this figure to anyone."
)
EXPLORATORY_BADGE = (
    "Figures computed and checked against the query above. The query itself "
    "was chosen by a model."
)
NARRATION_BLOCKED_CAPTION = (
    "⚠ Model output blocked: a figure didn't verify. "
    "Showing the computed sentence instead."
)

# Filter values in a query description come from the model, so they're
# escaped before they reach markdown and can't restyle the line.
MARKDOWN_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>$~])")


def _markdown_escape(text: str) -> str:
    return MARKDOWN_SPECIALS.sub(r"\\\1", text)


# Nothing here sets a background or a text colour of its own. The app runs in
# whichever theme the reader has chosen, and painting a light panel into a
# dark theme is how a white sidebar ended up holding white text and a white
# collapse arrow. Every surface below is a translucent grey, which reads on
# both themes, and every text colour is the theme's own at reduced opacity.
#
# Streamlit's class names move between releases, so all of this is cosmetic by
# design: if a selector stops matching, the app still renders every figure,
# flag, row, and trace it did before, just less tidily.
STYLE = """
<style>
  .side-title { font-size: 1.02rem; font-weight: 650; margin: 0 0 .1rem 0; }
  .side-sub { font-size: .74rem; opacity: .65; margin: 0 0 .85rem 0; }
  .metric-name { font-size: .92rem; font-weight: 650; margin: .1rem 0 .25rem 0; }
  .pill {
    display: inline-block; font-size: .64rem; letter-spacing: .02em; opacity: .85;
    background: rgba(128,128,128,.16); border: 1px solid rgba(128,128,128,.22);
    border-radius: 999px; padding: .1rem .45rem; margin: 0 .25rem .3rem 0;
  }
  .metric-desc { font-size: .74rem; opacity: .7; line-height: 1.4; margin: 0 0 .45rem 0; }

  /* The one badge in the app that has to read as a warning rather than as
     a neutral label, so it borrows red rather than the grey every other
     pill uses - the same distinction the red banner above it draws. */
  .exploratory-pill {
    display: inline-block; font-size: .66rem; font-weight: 650; letter-spacing: .03em;
    text-transform: uppercase; color: #c0392b;
    background: rgba(192,57,43,.12); border: 1px solid rgba(192,57,43,.4);
    border-radius: 999px; padding: .12rem .5rem; margin: 0 0 .5rem 0;
  }

  .panel-heading {
    display: flex; align-items: center; gap: .35rem;
    font-size: .78rem; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; opacity: .8;
    margin: .9rem 0 .45rem 0; padding-bottom: .2rem;
    border-bottom: 1px solid rgba(128,128,128,.25);
  }
  .sub-heading {
    display: flex; align-items: center; gap: .35rem;
    font-size: .72rem; opacity: .68; margin: .6rem 0 .3rem 0;
  }

  .defn-box {
    background: rgba(128,128,128,.07); border: 1px solid rgba(128,128,128,.22);
    border-radius: 8px; padding: .6rem .7rem;
  }
  .defn { font-size: .745rem; opacity: .82; line-height: 1.42; margin: 0 0 .55rem 0; }
  .defn:last-child { margin-bottom: 0; }

  .caveat-title { font-size: .82rem; font-weight: 650; margin: 0 0 .2rem 0; }
  .caveat-body { font-size: .755rem; opacity: .8; line-height: 1.42; margin: 0; }

  /* A list of deal IDs is data, so it is laid out as data rather than run
     together into a paragraph of comma-separated prose. */
  .chips { display: flex; flex-wrap: wrap; gap: .25rem; margin-top: .45rem; }
  .chip {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: .66rem; padding: .08rem .35rem; border-radius: 4px; opacity: .85;
    background: rgba(128,128,128,.14); border: 1px solid rgba(128,128,128,.22);
    white-space: nowrap;
  }

  .info {
    display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; min-width: 15px; border-radius: 50%;
    border: 1px solid rgba(128,128,128,.55);
    font-size: .62rem; font-weight: 700; line-height: 1; font-style: italic;
    text-transform: none; letter-spacing: 0; opacity: .65;
    cursor: help; position: relative;
  }
  .info:hover, .info:focus { opacity: 1; }
  .info .tip {
    visibility: hidden; opacity: 0; transition: opacity .12s ease;
    position: absolute; left: 0; top: calc(100% + 7px); z-index: 9999;
    width: 265px; padding: .55rem .65rem; border-radius: 6px;
    background: #1f2329; color: #f5f5f5;
    border: 1px solid rgba(255,255,255,.14);
    box-shadow: 0 6px 18px rgba(0,0,0,.4);
    font-size: .7rem; font-weight: 400; font-style: normal; line-height: 1.45;
    text-transform: none; letter-spacing: normal; text-align: left;
  }
  .info:hover .tip, .info:focus .tip { visibility: visible; opacity: 1; }

  [data-testid="stMetric"] { padding: .2rem .1rem; }
  [data-testid="stMetricLabel"] p { font-size: .7rem !important; opacity: .75; }
  [data-testid="stMetricValue"] { font-size: 1.02rem; }

  /* The chat stays put while the details panel scrolls past it. Without
     align-self the column stretches to the full row height and a stretched
     flex item has nothing left to stick against. */
  [data-testid="stColumn"]:has(#chat-anchor) {
    position: sticky; top: 3.2rem; align-self: flex-start;
  }

  /* The transcript is sized against the viewport rather than pinned to a
     fixed pixel height. A pinned column taller than the window puts its own
     chat input below the fold, which is the one thing a chat window must
     never do, and a fixed height also wastes the extra room a taller screen
     has. The Python side still passes a height, since st.container requires
     one; this is what makes it adapt. The rule matches the one wrapper
     holding the keyed transcript, which keeps it off any other layout
     wrapper added to the chat column later and off the message containers
     nested inside the transcript. The override is on `flex`, not `height`: the container is a
     flex item whose size comes from flex-basis, which wins over height on
     the main axis, so setting height alone does nothing. */
  [data-testid="stColumn"]:has(#chat-anchor)
    > [data-testid="stVerticalBlock"]
    > [data-testid="stLayoutWrapper"]:has(> .st-key-transcript) {
    flex: 0 0 calc(100vh - 20.5rem) !important;
    height: calc(100vh - 20.5rem) !important;
    min-height: 240px;
  }
</style>
"""

# What each panel section is, in the words a sales leader would want rather
# than the words the code uses. Rendered as a hover affordance beside the
# heading, so the explanation is available without spending panel space on it.
SECTION_INFO = {
    "figures": (
        "Every number behind this answer, computed from the deal rows by pandas. "
        "The model that writes the prose may only use figures listed here, and "
        "each one it writes is checked against this list before you see it."
    ),
    "flags": (
        "The assumptions and caveats this answer rests on. All of them are shown "
        "without clicking, so nothing here can surprise you later in a meeting."
    ),
    "definitions": (
        "What each term means in this system, in plain English. This text is the "
        "same on every answer for a given metric, which is why it sits quieter "
        "than the caveats above it."
    ),
    "source_rows": (
        "The actual deal rows the answer was computed from, with the filter that "
        "produced them, the row count, and which snapshot they came from. Every "
        "figure above is reproducible by hand from these rows."
    ),
    "trace": (
        "How the question was read: the structured intent the router produced, "
        "whether routing ran online or fell back to keywords, and which snapshot "
        "answered. Use it to tell a routing mistake from a computation mistake."
    ),
    "catalog": (
        "Everything the system can answer, read from the metric registry itself "
        "rather than a written list. Click any example to ask it."
    ),
}


def _typewriter(text: str) -> Iterator[str]:
    """Yield `text` word by word, for `st.write_stream`'s typewriter effect.

    This never streams a raw model call. The narrator's prose (or the template
    fallback) is already fully generated and verified by the time this runs, so
    there is nothing here that could reveal a number before the verifier has
    checked it. The typing effect is cosmetic, replayed over text already final.
    """
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(WORD_DELAY_SECONDS)


def _render_answer(answer: Answer, *, stream: bool) -> None:
    """Render one assistant turn. `stream` is only ever True for the answer
    just computed in this run, so replayed history renders instantly and an
    old message never re-types itself on a later rerun."""
    if answer.router_mode == "offline":
        st.warning(
            "Offline routing: the model API was unreachable, so the keyword "
            "router answered this one. Double-check the restatement below."
        )
    if isinstance(answer, Refused):
        st.warning(f"I can't answer that: {answer.reason}")
        st.caption(answer.hint)
        if answer.intent is not None:
            st.caption(answer.intent.restated)
        return

    if answer.intent is not None and answer.intent.follows_up:
        # A standalone answer leaves its restatement to the trace panel. A
        # follow-up can't: what it carried over from the last question is
        # the one thing the reader has to check, so it leads the answer.
        st.caption(f"↳ {answer.intent.restated}")

    if answer.lane == "exploratory":
        # The warning comes first, above the answer, in the strongest
        # treatment the interface has. The query follows it straight away
        # and is never behind a click, since it's the one thing about this
        # answer a reader can't otherwise check. It shows twice: in plain
        # English for the reader, then as the pandas an analyst can rerun.
        st.markdown("<span class='exploratory-pill'>Exploratory</span>", unsafe_allow_html=True)
        st.error(EXPLORATORY_WARNING)
        st.markdown(f"**Query:** {_markdown_escape(answer.query_description)}")
        if answer.change_from_previous:
            # A refinement reads as a difference from the last query, so the
            # reader checks one change instead of rereading the whole query.
            st.caption(_markdown_escape(answer.change_from_previous))
        st.code(answer.expression, language="python", wrap_lines=True)

    if stream:
        st.write_stream(_typewriter(answer.prose))
    else:
        st.write(answer.prose)
    if answer.lane == "exploratory":
        st.caption(EXPLORATORY_BADGE)
        if answer.narrator_blocked:
            st.caption(NARRATION_BLOCKED_CAPTION)
    elif answer.prose_source == "narrator":
        st.caption(f"✓ {answer.verified_figures} figures verified against computed values")
    elif answer.narrator_blocked:
        st.caption(NARRATION_BLOCKED_CAPTION)


def _info(key: str) -> str:
    """A hover affordance carrying the plain-English explanation of a section.

    `tabindex` is what lets it open on keyboard focus as well as on hover, so
    the explanation isn't mouse-only.
    """
    if key not in SECTION_INFO:
        return ""
    text = html.escape(SECTION_INFO[key])
    return f"<span class='info' tabindex='0' role='note'>i<span class='tip'>{text}</span></span>"


def _heading(text: str, info: str | None = None) -> None:
    st.markdown(
        f"<div class='panel-heading'>{html.escape(text)}{_info(info or '')}</div>",
        unsafe_allow_html=True,
    )


def _render_flags(flags: tuple[Flag, ...]) -> None:
    """Caveats first and prominent, definitions after and quieter.

    A caveat is specific to this answer and is the thing a leader would be
    embarrassed to be surprised by. A definition is static reference text,
    identical on every answer for a given metric, which is why it can carry
    less weight without carrying less presence. Neither is behind a click.
    """
    caveats = [f for f in flags if not f.kind.startswith("definition:")]
    definitions = [f for f in flags if f.kind.startswith("definition:")]

    for flag in caveats:
        with st.container(border=True):
            body = (
                f"<p class='caveat-title'>{html.escape(flag.title)}</p>"
                f"<p class='caveat-body'>{html.escape(flag.lede)}</p>"
            )
            # A caveat naming forty-nine deals reads as a wall when its list is
            # run together as prose. The same IDs as chips stay every bit as
            # visible and become something you can actually pick a deal out of.
            if flag.items:
                chips = "".join(
                    f"<span class='chip'>{html.escape(item)}</span>" for item in flag.items
                )
                body += f"<div class='chips'>{chips}</div>"
            st.markdown(body, unsafe_allow_html=True)

    if definitions:
        st.markdown(
            f"<div class='sub-heading'>Definitions this answer rests on"
            f"{_info('definitions')}</div>",
            unsafe_allow_html=True,
        )
        items = "".join(
            f"<p class='defn'><b>{html.escape(f.title)}.</b> {html.escape(f.detail)}</p>"
            for f in definitions
        )
        st.markdown(f"<div class='defn-box'>{items}</div>", unsafe_allow_html=True)


def _render_figures(answer: Answered) -> None:
    """The chart first, then every fact in a two-column grid.

    All twelve facts stay on screen. Two per row rather than one turns a
    column you scroll past into a block you scan, without dropping any.
    """
    chart = chart_for(answer)
    if chart is not None:
        st.altair_chart(chart, width="stretch")

    facts = list(answer.facts.values())
    for start in range(0, len(facts), 2):
        columns = st.columns(2)
        for column, fact in zip(columns, facts[start : start + 2]):
            column.metric(fact.label, fact.formatted())


@st.cache_resource
def get_data():
    return load_data()


@st.cache_resource
def get_client() -> anthropic.Anthropic | None:
    """None when the API key is missing, so routing falls back offline instead
    of crashing the app at startup."""
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


@st.cache_resource
def get_query_log() -> QueryLog:
    return QueryLog(config.QUERY_LOG_PATH)


st.markdown(STYLE, unsafe_allow_html=True)

data = get_data()
client = get_client()
query_log = get_query_log()
catalog = build_catalog(data)

if "history" not in st.session_state:
    st.session_state.history = []  # list of (question, Answer)
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

with st.sidebar:
    st.markdown(
        "<div class='side-title'>Acme pipeline assistant</div>"
        f"<div class='side-sub'>As of {data.as_of} · routed by {config.ROUTER_MODEL}</div>",
        unsafe_allow_html=True,
    )
    # Clears what the assistant remembers along with the transcript, so a new
    # line of questions never follows on from an old one. In the sidebar, not
    # beside the chat heading, since a taller heading pushes the chat input
    # below the fold on a short window.
    if st.button("New conversation", disabled=not st.session_state.history, width="stretch"):
        st.session_state.history = []
        st.rerun()
    st.markdown(
        f"<div class='panel-heading'>What I can answer{_info('catalog')}</div>",
        unsafe_allow_html=True,
    )

    for spec in catalog.metrics:
        pills = "".join(f"<span class='pill'>{html.escape(g)}</span>" for g in spec.groupings)
        st.markdown(
            f"<div class='metric-name'>{html.escape(spec.name)}</div>{pills}"
            f"<p class='metric-desc'>{html.escape(spec.description)}</p>",
            unsafe_allow_html=True,
        )
        # Example questions are clickable rather than quoted, so a demo
        # audience can run one instead of retyping it. Still read from the
        # catalog, so nothing here can drift out of sync with the registry.
        for index, example in enumerate(spec.examples):
            if st.button(example, key=f"example-{spec.name}-{index}", width="stretch"):
                st.session_state.pending_question = example
                st.rerun()
        st.divider()

chat_col, panel_col = st.columns([1, 1], gap="large")

with chat_col:
    # The marker the sticky rule in STYLE keys off. Streamlit gives no way to
    # put a class on a column, so the column is selected by what it contains.
    st.markdown("<div id='chat-anchor'></div>", unsafe_allow_html=True)
    st.subheader("Chat")
    transcript = st.container(height=TRANSCRIPT_HEIGHT, border=True, key="transcript")

    with transcript:
        for question, answer in st.session_state.history:
            with st.chat_message("user"):
                st.write(question)
            with st.chat_message("assistant"):
                _render_answer(answer, stream=False)

    placeholder_example = catalog.examples()[0]
    typed = st.chat_input(f'Ask about pipeline, e.g. "{placeholder_example}"')
    question = typed or st.session_state.pending_question
    st.session_state.pending_question = None

    if question:
        with transcript:
            with st.chat_message("user"):
                st.write(question)
            # Earlier turns reach the models as readings, never as answers,
            # so a follow-up like "what about SMB" has something to follow.
            memory = remember(turn(q, a) for q, a in st.session_state.history)
            answer = ask(question, data, client, log=query_log, history=memory)
            with st.chat_message("assistant"):
                # Streamed only here, for the answer this run just computed.
                # Every later rerun draws it from `history` above, instantly.
                _render_answer(answer, stream=True)
        # No rerun here. The details panel below reads `history[-1]` in this
        # same pass, so it already shows this answer, and rerunning would
        # redraw the prose the reader just watched type itself in.
        st.session_state.history.append((question, answer))

with panel_col:
    st.subheader("Details")
    latest = st.session_state.history[-1][1] if st.session_state.history else None

    if latest is None:
        st.info("Ask a question to see the figures, flags, source rows, and trace here.")
    elif isinstance(latest, Refused):
        _heading("Refused")
        st.write(latest.reason)
        _heading("Coverage")
        st.write(latest.hint)
        if latest.intent is not None:
            _heading("Trace", "trace")
            st.json(latest.intent.model_dump())
    else:
        answer: Answered = latest

        _heading("Figures", "figures")
        _render_figures(answer)

        _heading("Flags", "flags")
        _render_flags(answer.flags)

        _heading("Source rows", "source_rows")
        st.caption(f"{answer.row_count} rows · snapshot: {answer.snapshot}")
        for key, value in answer.filters.items():
            st.caption(f"{key}: {value}")
        st.dataframe(answer.source_rows, width="stretch", hide_index=True)

        _heading("Trace", "trace")
        st.caption(f"Router: {answer.router_mode}")
        st.caption(f"Snapshot answering: {answer.snapshot}")
        if answer.intent is not None:
            st.json(answer.intent.model_dump())
        elif answer.lane == "exploratory":
            # No structured Intent exists for this lane - it never went
            # through the router's reading - so the restatement is what
            # stands in for the trace an intent would otherwise give.
            st.caption(answer.restated)
