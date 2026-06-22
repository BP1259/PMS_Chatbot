"""
app.py — Streamlit Web UI
API key loaded automatically from .env / st.secrets (never shown in UI)
"""

import base64
import re
import streamlit as st
from dotenv import load_dotenv
from logo_data import LOGO_B64

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
st.markdown("""<style>
:root{--navy:#0b1f3a;--blue:#1769e0;--bg:#dbe6f1;--border:#dfe5ee;--text:#172033;--muted:#667085}
.stApp{background:linear-gradient(135deg,#afc3d8 0%,#c3d3e3 48%,#b5c9dc 100%);color:var(--text)}[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1120px;padding-top:1.4rem;padding-bottom:7rem}
section[data-testid="stSidebar"]{background:var(--navy);border:0}section[data-testid="stSidebar"] *{color:#f8fafc}
section[data-testid="stSidebar"] .stButton>button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);color:#fff;border-radius:10px;min-height:2.55rem;text-align:left;justify-content:flex-start}
section[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,255,255,.16)}
.bp-logo{background:transparent;border-radius:14px;padding:14px 20px;margin:2px 0 18px;text-align:center}.bp-logo img{width:82%;max-width:180px}
.bp-label{color:#a8b7cc!important;font-size:.71rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;margin:1rem 0 .4rem}
.bp-resource{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:12px;padding:14px}.bp-resource a{color:#fff!important;font-weight:700;text-decoration:none}.bp-resource p{color:#bdc9d8!important;font-size:.78rem;margin:.45rem 0 0}
.bp-hero{background:linear-gradient(135deg,#0b1f3a,#123a70 68%,#1769e0);border-radius:18px;color:#fff;padding:26px 30px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 14px 32px rgba(11,31,58,.16);margin-bottom:1.4rem}
.bp-hero h1{color:#fff;font-size:1.65rem;margin:.35rem 0 .5rem}.bp-hero p{color:#d9e5f5;margin:0;max-width:680px;font-size:.94rem}.bp-kicker{color:#9fc5ff;font-size:.72rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.bp-status{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:999px;padding:8px 12px;white-space:nowrap;font-size:.78rem;font-weight:700}.bp-dot{display:inline-block;width:8px;height:8px;margin-right:7px;border-radius:50%;background:#50d3a1}
.bp-welcome{background:#fff;border:1px solid var(--border);border-radius:16px;padding:22px 24px 10px;margin-bottom:1rem;box-shadow:0 5px 18px rgba(16,24,40,.045)}.bp-welcome h2{font-size:1.2rem;margin:0 0 .35rem}.bp-welcome p{color:var(--muted);margin:0;font-size:.9rem}
.bp-card{background:#fff;border:1px solid var(--border);border-radius:14px;min-height:112px;padding:16px;margin-bottom:.6rem}.bp-card strong{display:block;margin-bottom:.35rem}.bp-card span{color:var(--muted);font-size:.82rem;line-height:1.45}
div[data-testid="stButton"]>button{border-radius:10px;border:1px solid #cfd8e6;font-weight:600;min-height:2.55rem}
[data-testid="stChatMessage"]{background:rgba(239,245,251,.94);border:1px solid #cfdae8;border-radius:14px;padding:.35rem .65rem;margin-bottom:.75rem;box-shadow:0 3px 12px rgba(16,24,40,.035)}
[data-testid="stBottom"],[data-testid="stBottomBlockContainer"],[data-testid="stChatInput"]{background:linear-gradient(90deg,#afc3d8 0%,#c3d3e3 50%,#b5c9dc 100%)!important}[data-testid="stChatInput"]{padding-top:.65rem}[data-testid="stChatInput"]>div{border:1px solid #cbd5e1;border-radius:14px;box-shadow:0 8px 24px rgba(11,31,58,.1)}[data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li,[data-testid="stChatMessage"] div,[data-testid="stChatInput"] textarea{color:#101828!important}
@media(prefers-color-scheme:dark){.stApp{background:linear-gradient(135deg,#091422 0%,#12263a 48%,#0d1d2e 100%);color:#f4f7fb}[data-testid="stBottom"],[data-testid="stBottomBlockContainer"],[data-testid="stChatInput"]{background:linear-gradient(90deg,#091422 0%,#12263a 50%,#0d1d2e 100%)!important}[data-testid="stChatMessage"]{background:rgba(23,42,64,.96);border-color:#38516c;box-shadow:0 4px 14px rgba(0,0,0,.22)}[data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li,[data-testid="stChatMessage"] div,[data-testid="stChatInput"] textarea{color:#f4f7fb!important}[data-testid="stChatInput"]>div{background:#172a40;border-color:#49637f}[data-testid="stChatInput"] textarea::placeholder{color:#aebed0!important}.bp-welcome,.bp-card{background:#14263a;border-color:#38516c;color:#f4f7fb}.bp-welcome h2,.bp-card strong{color:#f4f7fb}.bp-welcome p,.bp-card span{color:#b8c7d8}div[data-testid="stButton"]>button{background:#172a40;color:#edf4fb;border-color:#49637f}a{color:#75aaff!important}hr{border-color:#38516c!important}}@media(max-width:768px){section[data-testid="stSidebar"]{min-width:86vw!important;max-width:86vw!important}.block-container{padding:.8rem .85rem 6.5rem}.bp-hero{padding:20px}.bp-hero h1{font-size:1.3rem}.bp-status{display:none}}
</style>""",unsafe_allow_html=True)

# Manual theme override. The sidebar toggle persists in session state.
if st.session_state.get("dark_mode", False):
    st.markdown("""<style>
    .stApp{background:linear-gradient(135deg,#091422 0%,#12263a 48%,#0d1d2e 100%)!important;color:#f4f7fb!important}
    [data-testid="stBottom"],[data-testid="stBottomBlockContainer"],[data-testid="stChatInput"]{background:linear-gradient(90deg,#091422 0%,#12263a 50%,#0d1d2e 100%)!important}
    [data-testid="stChatMessage"]{background:rgba(23,42,64,.96)!important;border-color:#38516c!important}
    [data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li,[data-testid="stChatMessage"] div,[data-testid="stChatInput"] textarea{color:#f4f7fb!important}
    [data-testid="stChatInput"]>div{background:#172a40!important;border-color:#49637f!important}
    [data-testid="stChatInput"] [data-baseweb="textarea"],[data-testid="stChatInput"] [data-baseweb="textarea"]>div,[data-testid="stChatInput"] textarea{background:#172a40!important;color:#f4f7fb!important;-webkit-text-fill-color:#f4f7fb!important}
    [data-testid="stChatInput"] textarea::placeholder{color:#aebed0!important}
    .bp-welcome,.bp-card{background:#14263a!important;border-color:#38516c!important;color:#f4f7fb!important}
    .bp-welcome h2,.bp-card strong{color:#f4f7fb!important}.bp-welcome p,.bp-card span{color:#b8c7d8!important}
    div[data-testid="stButton"]>button{background:#172a40;color:#edf4fb;border-color:#49637f}
    </style>""", unsafe_allow_html=True)
else:
    st.markdown("""<style>
    .stApp{background:linear-gradient(135deg,#afc3d8 0%,#c3d3e3 48%,#b5c9dc 100%)!important;color:#172033!important}
    [data-testid="stBottom"],[data-testid="stBottomBlockContainer"],[data-testid="stChatInput"]{background:linear-gradient(90deg,#afc3d8 0%,#c3d3e3 50%,#b5c9dc 100%)!important}
    [data-testid="stChatMessage"]{background:rgba(239,245,251,.96)!important;border-color:#cfdae8!important}
    [data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li,[data-testid="stChatMessage"] div,[data-testid="stChatInput"] textarea{color:#101828!important}
    [data-testid="stChatInput"]>div{background:#f7f9fc!important;border-color:#aebed0!important}
    [data-testid="stChatInput"] [data-baseweb="textarea"],[data-testid="stChatInput"] [data-baseweb="textarea"]>div,[data-testid="stChatInput"] textarea{background:#f7f9fc!important;color:#101828!important;-webkit-text-fill-color:#101828!important}
    .bp-welcome,.bp-card{background:#fff!important;border-color:#dfe5ee!important;color:#172033!important}
    .bp-welcome h2,.bp-card strong{color:#172033!important}.bp-welcome p,.bp-card span{color:#667085!important}
    </style>""", unsafe_allow_html=True)

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

from rag_engine import get_secret, ask, make_fw_client, PMS_RESOURCE_LINK
# PMS_RESOURCE_LINK is still used for the sidebar's permanent video/docs link.

FIREWORKS_API_KEY = get_secret("FIREWORKS_API_KEY")
SUPABASE_DB_URL   = get_secret("SUPABASE_DB_URL")


# ── Cached clients ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="🔌 Connecting to Fireworks.ai...")
def _fw_client():
    return make_fw_client(FIREWORKS_API_KEY)

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
with st.sidebar:
    st.markdown(f"""<div class="bp-logo"><img src="data:image/png;base64,{LOGO_B64}" alt="Bachaa Party"></div>""",unsafe_allow_html=True)
    st.toggle("Dark mode", key="dark_mode", help="Switch between light and dark appearance.")

    if st.button("Start new conversation",use_container_width=True,type="primary"):
        st.session_state.messages=[];st.session_state.history=[];st.session_state.pending=None;st.rerun()
    st.markdown('<div class="bp-label">Support area</div>',unsafe_allow_html=True)
    options=["Employee","Line Manager","Guidelines"]
    if "role" not in st.session_state: st.session_state.role="Employee"
    role=st.radio("Support area",options,key="role",label_visibility="collapsed")
    examples={"Employee":["How do I log in to HRMS?","How do I enter my goals?","How do I submit my self evaluation?","What are the do's and don'ts?"],"Line Manager":["Where are pending evaluations?","How do I rate a subordinate?","How do I submit an appraisal?","How do I edit a completed appraisal?"],"Guidelines":["Show me all the guidelines","What is the eligibility criteria?","What is the appraisal timeline?","What are the grace marks rules?"]}
    st.markdown('<div class="bp-label">Common questions</div>',unsafe_allow_html=True)
    for i,ex in enumerate(examples[role]):
        if st.button(ex,key=f"side_{role}_{i}",use_container_width=True): st.session_state.pending=ex;st.rerun()
    st.markdown('<div class="bp-label">Company</div>',unsafe_allow_html=True)
    if st.button("About Bachaa Party",key="about_bp",use_container_width=True): st.session_state.pending="About Bachaa Party";st.rerun()
    st.markdown('<div class="bp-label">Training resources</div>',unsafe_allow_html=True)
    st.markdown(f"""<div class="bp-resource"><a href="{PMS_RESOURCE_LINK}" target="_blank">Open tutorial and documents</a><p>Official walkthroughs and supporting appraisal material.</p></div>""",unsafe_allow_html=True)

# MAIN
st.markdown("""<div class="bp-hero"><div><div class="bp-kicker">Performance Management System</div><h1>Appraisal Training &amp; Support</h1><p>Clear guidance for employees and line managers, grounded in official appraisal documentation.</p></div><div class="bp-status"><span class="bp-dot"></span>Knowledge base ready</div></div>""",unsafe_allow_html=True)

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


if not st.session_state.messages:
    st.markdown("""<div class="bp-welcome"><h2>How can we help today?</h2><p>Select your support area or start with a common task.</p></div>""",unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    cards=[("Employee guidance","Goals, self-evaluation, login, submission, and process instructions.","Enter or update goals","How do I enter my goals?"),("Line manager guidance","Evaluations, ratings, comments, submissions, and completed appraisals.","Review a subordinate","How do I rate my subordinate's appraisal?"),("Policies and timelines","Eligibility, scoring, grace marks, deadlines, and annual rules.","View appraisal guidelines","Show me all the guidelines")]
    for col,(title,body,label,question) in zip((c1,c2,c3),cards):
        with col:
            st.markdown(f"""<div class="bp-card"><strong>{title}</strong><span>{body}</span></div>""",unsafe_allow_html=True)
            if st.button(label,key=f"welcome_{label}",use_container_width=True): st.session_state.pending=question;st.rerun()

# ── Chat input ─────────────────────────────────────────────────────────────
# Resolve the prompt BEFORE rendering history, so we know whether this run
# is about to add a new turn. This avoids placing latest-turn-anchor twice
# (once in history, once in the live block) which would create a duplicate
# DOM id — getElementById always returns the first match in document order,
# so a leftover anchor from history (pointing at the PREVIOUS question)
# would silently win over the new one, making the page scroll to the start
# of the chat instead of the new turn.
#
# IMPORTANT: st.chat_input() is called UNCONDITIONALLY on every run, even
# when a sidebar button already supplied a `pending` prompt this run. If
# chat_input() is skipped on a run (e.g. wrapped in `if prompt is None`),
# Streamlit can fail to re-mount the input box on the next run, leaving the
# user with no visible text box until a full state reset (New Chat). Always
# calling it avoids that, and we simply ignore its return value on runs
# where a button-supplied prompt takes priority.
typed_prompt = st.chat_input("Ask anything about the appraisal system…")
prompt = st.session_state.pending
st.session_state.pending = None
if prompt is None:
    prompt = typed_prompt

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
        response_placeholder = st.empty()
        response_placeholder.markdown("_Thinking…_")
        emitted = {"length": 0}

        def on_delta(text):
            # Throttle frequent UI updates while keeping the response visibly
            # live. The complete answer is always rendered after streaming.
            if (
                len(text) - emitted["length"] >= 12
                or text.endswith(("\n", ".", "!", "?", ":"))
            ):
                emitted["length"] = len(text)
                response_placeholder.markdown(text + " ▌")

        try:
            answer, sources = ask(
                fw_client,
                prompt,
                st.session_state.history,
                on_delta=on_delta,
            )
        except Exception as e:
            answer = f"❌ Error: {e}"
            sources = []

        response_placeholder.markdown(answer)
        _render_interleaved_steps(sources)

    st.session_state.messages.append({
        "role":    "assistant",
        "content": answer,
        "sources": sources,
    })
    st.session_state.history.append({"role": "user",      "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": answer})
