"""
app.py — Streamlit Web UI
API key loaded automatically from .env / st.secrets (never shown in UI)
"""

import os
import base64
import re
import streamlit as st
from dotenv import load_dotenv
from logo_data import LOGO_B64
import streamlit.components.v1 as components

load_dotenv()

st.set_page_config(
    page_title="BP Online Appraisal System Training & Support",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="auto",  # collapsed on mobile, expanded on desktop
)

# ── Mobile responsiveness ────────────────────────────────────────────────
# Streamlit's own breakpoint for "auto" is ~768px, but we reinforce it here
# and tune a few things specifically for small screens: a roomier sidebar
# toggle (easier to tap), a slightly narrower sidebar so it doesn't eat the
# whole viewport, and tighter title/logo spacing so the header doesn't wrap
# awkwardly on narrow phones.
st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        /* Sidebar takes most — but not all — of the screen when opened,
           so users can still see a sliver of the chat behind it. */
        section[data-testid="stSidebar"] {
            min-width: 82vw !important;
            max-width: 82vw !important;
        }

        /* Make the collapse/expand arrow easier to tap on touch screens */
        button[data-testid="stSidebarCollapseButton"],
        button[data-testid="baseButton-headerNoPadding"] {
            transform: scale(1.3);
        }

        /* Reduce top padding so content starts higher on small screens */
        .block-container {
            padding-top: 1rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }

        /* Shrink the header title/logo row so it doesn't wrap oddly */
        h1 {
            font-size: 1.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "conversation" not in st.session_state:
    st.session_state.conversation = None
if "initialized" not in st.session_state:
    st.session_state.initialized = False
if "user_input" not in st.session_state:
    st.session_state.user_input = ""

show_sources = False

from rag_engine import get_secret, ask, make_fw_client, chunk_count, PMS_RESOURCE_LINK
# PMS_RESOURCE_LINK is still used for the sidebar's permanent video/docs link.

FIREWORKS_API_KEY = get_secret("FIREWORKS_API_KEY")
SUPABASE_DB_URL   = get_secret("SUPABASE_DB_URL")


# ── Cached clients ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="🔌 Connecting to Fireworks.ai...")
def _fw_client():
    return make_fw_client(FIREWORKS_API_KEY)

@st.cache_resource(show_spinner="📚 Loading knowledge base...")
def _db_count():
    try:
        return chunk_count()
    except Exception as e:
        return f"error: {e}"

@st.cache_resource(show_spinner="🤖 Waking up the AI model (first load can take up to a minute)...")
def _warm_embed_model():
    from rag_engine import _get_embed_model
    return _get_embed_model()


# ══════════════════════════════════════════════════════════════════════════
# INTERLEAVED STEP RENDERER
# ══════════════════════════════════════════════════════════════════════════
def _render_interleaved_steps(sources: list):
    """
    Show step screenshots followed immediately by their detailed instructions.
    Works for both PMS employee chunks and LM guide chunks — same schema.
    """
    rendered = set()
    ordered_chunks = sorted(sources, key=lambda x: x.get("step_number", 0))

    for s in ordered_chunks:
        chunk_id = s.get("id")
        if chunk_id and chunk_id not in rendered:
            step_num = s.get("step_number", 0)

            if s.get("has_image") and s.get("image_data"):
                try:
                    img_bytes = base64.b64decode(s["image_data"])
                    caption = (
                        f"📸 Step {step_num}: {s.get('step_title','')}"
                        if step_num > 0
                        else f"📸 {s.get('step_title','')}"
                    )
                    try:
                        st.image(img_bytes, caption=caption, use_container_width=True)
                    except TypeError:
                        st.image(img_bytes, caption=caption, use_column_width=True)
                except Exception:
                    pass

            raw_text = s["text"].split("---")[0].strip()
            lines = raw_text.split("\n")
            clean_lines = [
                l for l in lines
                if not l.startswith("Section:") and not re.match(r"^Step \d+:", l)
            ]
            detail_text = "\n".join(clean_lines).strip()
            st.markdown(detail_text)
            st.divider()
            rendered.add(chunk_id)


# ══════════════════════════════════════════════════════════════════════════
# (Drive link button removed from answers — it's now permanent in the sidebar)
# ══════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        f'''
        <div style="display:flex; justify-content:center; align-items:center; padding:14px 0;">
            <img src="data:image/png;base64,{LOGO_B64}" style="width:65%; max-width:220px; height:auto;" />
        </div>
        ''',
        unsafe_allow_html=True
    )
    st.divider()

    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.history = []
        st.session_state.pending = None
        st.rerun()


    if FIREWORKS_API_KEY:
        st.success("✅ `FIREWORKS API KEY WORKING PROPERLY`")
    else:
        st.error("❌ FIREWORKS_API_KEY not set")

    st.divider()

    st.markdown("### 📹 Video Tutorial")
    st.markdown(
        f'<a href="{PMS_RESOURCE_LINK}" target="_blank" style="'
        f'display:inline-flex;align-items:center;gap:6px;'
        f'background:#1a73e8;color:white;text-decoration:none;'
        f'padding:6px 14px;border-radius:16px;font-size:13px;font-weight:500;">'
        f'📹 Video Tutorial &amp; Docs</a>',
        unsafe_allow_html=True,
    )
    st.caption("Video walkthrough + supporting documents for the BP Performance Appraisal System.")

    st.divider()

    # ── Employee (PMS) examples ────────────────────────────────────────────
    st.markdown("### 👤 Employee — Appraisal System")
    pms_examples = [
        "How do I log in to HRMS?",
        "How do I enter my goals?",
        "How do I submit my self evaluation?",
        "What are the do's and don'ts?",
        "Show me the video tutorial",
    ]
    for ex in pms_examples:
        if st.button(ex, key=f"pms_{ex[:30]}"):
            st.session_state.pending = ex
            st.rerun()

    st.divider()

    # ── Line Manager examples ──────────────────────────────────────────────
    st.markdown("### 👔 Line Manager — Appraisal System")
    lm_examples = [
        "How do I rate my subordinate's appraisal?",
        "Where do I find pending subordinate evaluations?",
        "How do I add comments for each goal?",
        "How do I submit the line manager appraisal?",
        "How do I edit a completed appraisal?",
        "What are the steps for line managers?",
    ]
    for ex in lm_examples:
        if st.button(ex, key=f"lm_{ex[:30]}"):
            st.session_state.pending = ex
            st.rerun()

    st.divider()


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
header_col, logo_col = st.columns([0.9, 0.1])
with header_col:
    st.title("📊 BP Online Appraisal System Training & Support")
with logo_col:
    st.markdown(
        f'<div style="display:flex; align-items:center; height:100%; padding-top:10px;">'
        f'<img src="data:image/png;base64,{LOGO_B64}" width="100"/></div>',
        unsafe_allow_html=True
    )
st.caption(
    "Ask about appraisal steps · 📸 Step screenshots · 📹 Video tutorial · "
    "👤 Employee guide · 👔 Line Manager guide"
)

st.divider()

counts = _db_count()
if isinstance(counts, int):
    if counts:
            st.success(f"✅ Knowledge base: Loaded Successfully")
    else:
            st.info("ℹ️ No guide data — run ingest_pms.py and ingest_lm.py")
else:
    st.error(f"❌ DB: {counts}")

if not FIREWORKS_API_KEY:
    st.error(
        "**FIREWORKS_API_KEY not configured.**\n\n"
        "- Local: add to `.env`\n"
        "- HF Spaces: Settings → Repository secrets → `FIREWORKS_API_KEY`"
    )
    st.stop()

if not SUPABASE_DB_URL:
    st.error(
        "**SUPABASE_DB_URL not configured.**\n\n"
        "- Local: add to `.env`\n"
        "- HF Spaces: Settings → Repository secrets → `SUPABASE_DB_URL`"
    )
    st.stop()

for key, default in [("messages", []), ("history", []), ("pending", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

fw_client = _fw_client()
_warm_embed_model()

# ── Chat input ─────────────────────────────────────────────────────────────
# Resolve the prompt BEFORE rendering history, so we know whether this run
# is about to add a new turn. This avoids placing latest-turn-anchor twice
# (once in history, once in the live block) which would create a duplicate
# DOM id — getElementById always returns the first match in document order,
# so a leftover anchor from history (pointing at the PREVIOUS question)
# would silently win over the new one, making the page scroll to the start
# of the chat instead of the new turn.
prompt = st.session_state.pending
st.session_state.pending = None
if prompt is None:
    prompt = st.chat_input("Ask anything about the appraisal system…")

# ── Render chat history ────────────────────────────────────────────────────
# Find the index of the most recent user message — that's the start of the
# latest Q&A turn, and where we'll anchor the auto-scroll. Skip this when a
# new prompt is about to be processed below; the live block owns the anchor
# for that case.
last_user_idx = None
if not prompt:
    last_user_idx = max(
        (i for i, m in enumerate(st.session_state.messages) if m["role"] == "user"),
        default=None,
    )

for i, msg in enumerate(st.session_state.messages):
    avatar = "🧑" if msg["role"] == "user" else "🤖"

    # Anchor right before the latest question, not after the whole chat.
    if i == last_user_idx:
        st.markdown('<div id="latest-turn-anchor"></div>', unsafe_allow_html=True)

    with st.chat_message(msg["role"], avatar=avatar):
        if msg["role"] == "assistant":
            sources = msg.get("sources", [])
            st.markdown(msg["content"])
            _render_interleaved_steps(sources)
        else:
            st.markdown(msg["content"])

# ── Process prompt ─────────────────────────────────────────────────────────
if prompt:
    # Anchor goes BEFORE the new question is rendered — this is the start
    # of the new turn, which is what we'll scroll to once it's generated.
    st.markdown('<div id="latest-turn-anchor"></div>', unsafe_allow_html=True)

    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                answer, sources = ask(fw_client, prompt, st.session_state.history)
            except Exception as e:
                answer  = f"❌ Error: {e}"
                sources = []

        st.markdown(answer)
        _render_interleaved_steps(sources)

    st.session_state.messages.append({
        "role":    "assistant",
        "content": answer,
        "sources": sources,
    })
    st.session_state.history.append({"role": "user",      "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": answer})

# ── Auto-scroll to start of latest answer ───────────────────────────────
# Scrolls to the anchor placed right before the latest question, so the
# user sees the start of the newest turn instead of being dropped past
# the end of the answer.
#
# Why a retry loop: this script fires the instant components.html() mounts,
# but step screenshots in the answer above (loaded via st.image) keep
# resizing the page as they decode/paint. A single scrollIntoView() lands
# correctly for a moment, then the growing page pushes it back down,
# which looks identical to "it scrolled to the bottom." Re-scrolling to
# the same anchor repeatedly over ~1.5s absorbs that layout shift.
components.html(
    """
    <script>
        (function () {
            var doc = window.parent.document;
            var attempts = 0;
            var maxAttempts = 15;       // ~1.5s total at 100ms intervals
            var lastTop = null;
            var stableCount = 0;

            function scrollToAnchor() {
                var anchor = doc.getElementById("latest-turn-anchor");
                if (!anchor) return;

                anchor.scrollIntoView({behavior: "smooth", block: "start"});

                var rect = anchor.getBoundingClientRect();
                if (lastTop !== null && Math.abs(rect.top - lastTop) < 2) {
                    stableCount += 1;
                } else {
                    stableCount = 0;
                }
                lastTop = rect.top;

                attempts += 1;
                // Stop once position has been stable for 3 checks in a row,
                // or after maxAttempts as a hard cap.
                if (stableCount < 3 && attempts < maxAttempts) {
                    setTimeout(scrollToAnchor, 100);
                }
            }

            // Small initial delay lets Streamlit finish the current paint
            // pass before we start measuring/scrolling.
            setTimeout(scrollToAnchor, 150);
        })();
    </script>
    """,
    height=0,
)