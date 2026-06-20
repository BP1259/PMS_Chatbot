"""
rag_engine.py — Intelligent RAG engine

Intent router:
  pms     -> pms_guide_chunks table (employee self-eval guide, steps 1-13)
  lm      -> lm_guide_chunks table  (line manager appraisal guide, steps 1-12)
  general -> LLM direct (no retrieval)

The LLM receives the FULL ordered guide as context in a single call and emits
a hidden <STEPS> tag listing which steps it used. The UI renders only those
screenshots. No vector search needed — guides are small enough to fit in context.
"""

from __future__ import annotations
import os
import re
from openai import OpenAI
import psycopg2
import psycopg2.pool
from pgvector.psycopg2 import register_vector

# ── Config ───────────────────────────────────────────────────────────────
FIREWORKS_BASE_URL  = "https://api.fireworks.ai/inference/v1"
MODEL               = "accounts/fireworks/models/deepseek-v4-pro"
TOP_K               = 8
TEMPERATURE         = 0.1
EMBED_MODEL         = "all-MiniLM-L6-v2"
RELEVANCE_THRESHOLD = 0.33

_MAX_TOKENS = {
    "pms":     2000,
    "lm":      2000,
    "general":  350,
}

PMS_RESOURCE_LINK = "https://drive.google.com/drive/folders/1aMOR9O57YafR6Jy9m5Kohiz_XG35v3h8"
# Note: the video/docs link is shown permanently in the sidebar — it is no
# longer injected into individual chat answers (see _call_llm / system prompts).
# ─────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

GENERAL_SYSTEM_PROMPT = """You are a helpful HR assistant for a retail company.
Answer warmly and concisely. No preamble. Maximum 80 words for simple questions.
Reply in the same language / script the user wrote in (English, Roman Urdu, Urdu script, etc.).
"""

PMS_SYSTEM_PROMPT = f"""You are an HR assistant helping EMPLOYEES use the BP Performance Appraisal System (HRMS at https://bachaaparty.flowhcm.com).

You will be given the COMPLETE employee step-by-step guide (all steps, in order) as context, plus the employee's question. The question may be phrased any way — full sentences, broken English, casual phrasing, or Roman Urdu (e.g. "mujhay apnay goals dalnay hain, kia karna chahiye" means "I need to enter my goals, what should I do"). Understand the MEANING and intent regardless of phrasing or language.

YOUR TASK:
1. Identify exactly which step(s) are relevant.
2. Reply in the SAME language / script the user used.
3. Give a brief, clear, conversational answer (2-5 sentences).
4. Mention any critical warnings relevant to those steps.
5. Do NOT dump raw step text — the UI shows screenshots and details separately.
6. Do NOT add conversational preamble like "I'd be happy to help".

MANDATORY: On the very last line of your response, output a tag listing the relevant step references, comma-separated:
<STEPS>6,7,8</STEPS>
- If login is relevant, include L first: <STEPS>L,1,2,3</STEPS>
- Steps range from 1-13. Steps 1-9 = Goals Input. Steps 10-13 = Self Evaluation.
- Always list in ascending order: L first (if present), then 1, 2, 3...
- If no specific steps apply, output: <STEPS></STEPS>

STRICT RULE — DO NOT BREAK: Never write the words "video", "tutorial", "Google Drive", "drive.google.com", or any link/URL anywhere in your response, even as a closing note, footer, or "for more info" line. The video tutorial is already shown permanently in the sidebar — repeating it is a mistake. End your response right after the last sentence of your answer (before the <STEPS> tag). No sign-offs, no "let me know if you need more help", no resource mentions.
"""

LM_SYSTEM_PROMPT = f"""You are an HR assistant helping LINE MANAGERS / HODs use the BP Performance Appraisal System (HRMS at https://bachaaparty.flowhcm.com) to conduct subordinate appraisals.

You will be given the COMPLETE Line Manager guide (all steps, in order) as context, plus the manager's question. Questions may be phrased any way — full sentences, broken English, casual phrasing, or Roman Urdu. Understand the MEANING and intent regardless of phrasing or language.

YOUR TASK:
1. Identify exactly which step(s) are relevant to the manager's question.
2. Reply in the SAME language / script the user used.
3. Give a brief, clear, conversational answer (2-5 sentences).
4. Mention any critical warnings relevant to those steps.
5. Do NOT dump raw step text — the UI shows screenshots and details separately.
6. Do NOT add conversational preamble like "I'd be happy to help".

MANDATORY: On the very last line of your response, output a tag listing the relevant step references, comma-separated:
<STEPS>3,4,5,6</STEPS>
- If login is relevant, include L first: <STEPS>L,1,2</STEPS>
- Steps range from 1-12. Steps 1-8 = Rating Subordinate Appraisals. Steps 9-12 = Editing a Completed Appraisal.
- Always list in ascending order: L first (if present), then 1, 2, 3...
- If no specific steps apply (e.g. general question), output: <STEPS></STEPS>

STRICT RULE — DO NOT BREAK: Never write the words "video", "tutorial", "Google Drive", "drive.google.com", or any link/URL anywhere in your response, even as a closing note, footer, or "for more info" line. The video tutorial is already shown permanently in the sidebar — repeating it is a mistake. End your response right after the last sentence of your answer (before the <STEPS> tag). No sign-offs, no "let me know if you need more help", no resource mentions.
"""


# ═══════════════════════════════════════════════════════════════════════════
# INTENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

_KPI_KEYWORDS = {
    "score", "scoring", "kpi", "discrepancy", "penalty", "penalties", "verbal", "written",
    "warning", "award", "level 1", "level 2", "no discrepancy", "customer service",
    "cross sell", "upsell", "up sell", "product knowledge",
    "matrix", "criteria", "threshold", "saaat", "sea", "guest", "sizzling",
    "mystery shopping", "cctv", "observation", "0.7", "0.8", "0.9", "1.0", "1.1", "1.2",
    "rating", "what score", "which score",
    "super transaction", "test call", "magic word",
}

# Line Manager specific keywords — checked BEFORE PMS keywords
_LM_KEYWORDS = {
    "line manager", "line manager review", "lm review",
    "subordinate", "subordinates", "hod", "head of department",
    "rate subordinate", "rating subordinate", "conduct appraisal",
    "pending evaluation", "pending appraisal", "pending subordinate",
    "edit appraisal", "edit completed", "update appraisal", "update performance evaluation",
    "completed appraisal", "filter by completed", "status completed",
    "appraisal meeting", "manager appraisal", "manager rating",
    "mera subordinate", "apna subordinate", "appraisal karni hai subordinate ki",
    "employee ki appraisal", "mujhe rate karna hai",
    "line manager wala", "lm wala", "manager wala form",
}

_PMS_KEYWORDS = {
    "appraisal", "performance appraisal", "pms", "hrms", "flowhcm", "bachaaparty",
    "log in", "login", "sign in", "password", "employee id",
    "goals", "goal", "objective", "kpi request", "objective-kpi",
    "new kpi", "+new kpi", "add kpi", "weightage", "weight",
    "submit goals", "send request", "pending approval",
    "self evaluation", "self-evaluation", "evaluate myself", "rate myself",
    "evaluation form", "submit evaluation", "submit appraisal",
    "company core values", "core values",
    "bell notification", "notification", "approved",
    "how to enter", "how do i enter", "how to submit", "how do i submit",
    "how to log", "how to login", "how to sign",
    "step 1", "step 2", "step 3", "step 4", "step 5",
    "step 6", "step 7", "step 8", "step 9", "step 10",
    "step 11", "step 12", "step 13",
    "performance request", "evaluations", "action dropdown",
    "others menu", "performance menu", "dashboard",
    "feedback to manager", "grace percentage",
    "video", "tutorial", "video tutorial", "watch", "drive link",
    "google drive", "training video", "training material", "resource",
    # Roman Urdu
    "goals dalna", "goal dalna", "goals dalni", "kpi dalna", "appraisal karni",
    "evaluation karni", "submit karni", "login karna", "sign in karna",
    "kia karna", "ab kia karna", "next kia",
}

_GENERAL_KEYWORDS = {
    "hello", "hi", "hey", "how are you", "good morning", "good afternoon",
    "good evening", "what's up", "whats up", "thank you", "bye", "goodbye",
    "joke", "story", "weather", "news", "what is hr", "human resources basics",
    "shukriya", "theek hai", "salam", "assalam",
}

_FORCE_GENERAL_PHRASES = [
    "thanks", "thank", "well done", "great job",
    "tell me a joke", "tell me about yourself", "what can you do",
]

_VIDEO_TRIGGERS = {
    "video", "video link", "tutorial", "video tutorial", "watch",
    "drive link", "google drive link", "link", "resource link",
    "training video", "training material", "show me the video",
    "where is the video", "send me the link", "give me the link",
    "share the link", "share link",
}


def _classify_intent(question: str) -> str:
    """Return 'pms', 'lm', or 'general'."""
    ql = question.lower().strip()

    if len(ql.split()) <= 2:
        greetings = {"hi", "hello", "hey", "thanks", "ok", "okay", "yes", "no", "bye",
                     "salam", "shukriya"}
        if any(g in ql for g in greetings):
            return "general"
        return "pms"

    lm_hits      = sum(1 for kw in _LM_KEYWORDS      if kw in ql)
    pms_hits     = sum(1 for kw in _PMS_KEYWORDS      if kw in ql)
    general_hits = sum(1 for kw in _GENERAL_KEYWORDS  if kw in ql)

    # LM keywords take highest priority — they are the most specific
    if lm_hits >= 1:
        return "lm"

    if pms_hits == 0 and any(p in ql for p in _FORCE_GENERAL_PHRASES):
        return "general"

    if pms_hits >= 1:
        return "pms"
    if general_hits >= 1 and pms_hits == 0:
        return "general"

    # Default to PMS
    return "pms"


# ═══════════════════════════════════════════════════════════════════════════
# SECRETS
# ═══════════════════════════════════════════════════════════════════════════

def get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, default)


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE — connection pool
# ═══════════════════════════════════════════════════════════════════════════

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        db_url = get_secret("SUPABASE_DB_URL")
        if not db_url:
            raise RuntimeError("SUPABASE_DB_URL not set.")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=15, dsn=db_url, connect_timeout=10
        )
    return _pool


class _DBConn:
    def __enter__(self):
        self.pool = _get_pool()
        self.conn = self.pool.getconn()
        register_vector(self.conn)
        return self.conn

    def __exit__(self, *_):
        self.pool.putconn(self.conn)


# ═══════════════════════════════════════════════════════════════════════════
# EMBEDDING MODEL
# ═══════════════════════════════════════════════════════════════════════════

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


# ═══════════════════════════════════════════════════════════════════════════
# FULL GUIDE FETCH — direct DB query (no vector search needed)
# ═══════════════════════════════════════════════════════════════════════════

def _row_to_dict(row) -> dict:
    return {
        "id":             row[0],
        "text":           row[1],
        "section":        row[2],
        "step_number":    row[3],
        "step_title":     row[4],
        "has_image":      row[5],
        "image_filename": row[6],
        "image_data":     row[7],
        "chunk_type":     row[8],
        "relevance":      1.0,
        "kpi":   "PMS Guide",
        "score": f"Step {row[3]}" if row[3] else row[2],
        "level": row[8],
    }


_GUIDE_ORDER_SQL = """
    ORDER BY
        CASE chunk_type
            WHEN 'overview'   THEN 0
            WHEN 'login_info' THEN 1
            WHEN 'step'       THEN 2
            ELSE 3
        END,
        step_number ASC
"""

# Per-table caches so guides aren't re-fetched on every message
_full_pms_guide_cache: list[dict] | None = None
_full_lm_guide_cache:  list[dict] | None = None


def _fetch_guide(doc_source: str, cache_attr: str) -> list[dict]:
    """Fetch all chunks for one doc_source from pms_guide_chunks (cached)."""
    cache = globals()[cache_attr]
    if cache is not None:
        return cache

    with _DBConn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, content, section, step_number, step_title,
                          has_image, image_filename, image_data, chunk_type
                   FROM pms_guide_chunks
                   WHERE doc_source = %s
                   {_GUIDE_ORDER_SQL}""",
                (doc_source,)
            )
            rows = cur.fetchall()

    result = [_row_to_dict(r) for r in rows]
    globals()[cache_attr] = result
    return result


def fetch_full_guide() -> list[dict]:
    """Fetch all employee guide chunks (doc_source='employee')."""
    return _fetch_guide("employee", "_full_pms_guide_cache")


def fetch_full_lm_guide() -> list[dict]:
    """Fetch all line manager guide chunks (doc_source='line_manager')."""
    return _fetch_guide("line_manager", "_full_lm_guide_cache")


def build_full_guide_context() -> str:
    parts = [c["text"] for c in fetch_full_guide()]
    return ("\n\n" + "─" * 50 + "\n\n").join(parts)


def build_full_lm_guide_context() -> str:
    parts = [c["text"] for c in fetch_full_lm_guide()]
    return ("\n\n" + "─" * 50 + "\n\n").join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# STEP TAG PARSING
# ═══════════════════════════════════════════════════════════════════════════

_STEPS_TAG_RE = re.compile(r"<STEPS>\s*([0-9A-Za-z,\s]*)\s*</STEPS>", re.IGNORECASE)

# Login is represented as -1 internally so it sorts before step 1
LOGIN_MARKER = -1


def _extract_steps_tag(text: str) -> tuple[str, list[int]]:
    """Remove <STEPS>...</STEPS> from visible text and return the ref list."""
    m = _STEPS_TAG_RE.search(text)
    if not m:
        return text, []

    raw = m.group(1).strip()
    refs: list[int] = []
    seen = set()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if part.upper() == "L":
                if LOGIN_MARKER not in seen:
                    refs.append(LOGIN_MARKER)
                    seen.add(LOGIN_MARKER)
            elif part.isdigit():
                n = int(part)
                if 1 <= n <= 13 and n not in seen:   # 13 covers both guides (LM max is 12)
                    refs.append(n)
                    seen.add(n)

    cleaned = _STEPS_TAG_RE.sub("", text).strip()
    return cleaned, refs


# ═══════════════════════════════════════════════════════════════════════════
# CHUNK RETRIEVAL BY STEP REFS
# ═══════════════════════════════════════════════════════════════════════════

def _get_chunks_by_refs(refs: list[int], all_chunks: list[dict]) -> list[dict]:
    """Generic helper — works for both PMS and LM chunk lists."""
    if not refs:
        return []
    wanted_steps = {r for r in refs if r != LOGIN_MARKER}
    wanted_login = LOGIN_MARKER in refs

    matched = []
    if wanted_login:
        matched.extend(c for c in all_chunks if c["chunk_type"] == "login_info")

    step_chunks = [
        c for c in all_chunks
        if c["chunk_type"] == "step" and c["step_number"] in wanted_steps
    ]
    step_chunks.sort(key=lambda x: x["step_number"])
    matched.extend(step_chunks)
    return matched


def get_chunks_by_refs(refs: list[int]) -> list[dict]:
    """Return PMS employee guide chunks matching refs (with images)."""
    return _get_chunks_by_refs(refs, fetch_full_guide())


def get_lm_chunks_by_refs(refs: list[int]) -> list[dict]:
    """Return Line Manager guide chunks matching refs (with images)."""
    return _get_chunks_by_refs(refs, fetch_full_lm_guide())


# ═══════════════════════════════════════════════════════════════════════════
# LLM CALL
# ═══════════════════════════════════════════════════════════════════════════

def _call_llm(client: OpenAI, messages: list[dict],
              max_tokens: int = 800, is_pms: bool = False) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if is_pms:
        text = _strip_video_link_mentions(text)

    return text


# Catches the model self-narrating a footer like "Video Tutorial & Supporting
# Documents <link>" even after being told not to. Splits the answer into
# sentences and drops any sentence containing the Drive URL, AND any
# sentence that is essentially just a label for the link ("Video Tutorial &
# Supporting Documents", "you can check the video here:") even if it ended
# up separated from the URL by the split. This is far more reliable than
# trying to regex-strip arbitrary surrounding phrasing in place. Safety net
# on top of the prompt instruction, not a replacement for it.
_DRIVE_URL_RE       = re.compile(r"https?://drive\.google\.com/\S+", re.IGNORECASE)
_SENTENCE_SPLIT_RE  = re.compile(r"(?<=[.!?:])\s+|\n+")
_LINK_LABEL_ONLY_RE = re.compile(
    r"(?i)^[\s\-—:,.]*"
    r"(you can (also )?check |see |watch |find |here.?s? )?"
    r"(the )?(📹\s*)?(video )?tutorial\s*(&|and)?\s*"
    r"(supporting documents)?\s*"
    r"(here)?[\s\-—:,.]*$"
)


def _strip_video_link_mentions(text: str) -> str:
    if not _DRIVE_URL_RE.search(text):
        return text

    sentences = _SENTENCE_SPLIT_RE.split(text)
    kept = []
    for s in sentences:
        st = s.strip()
        if not st or st == "---":
            continue
        if _DRIVE_URL_RE.search(s):
            continue
        if _LINK_LABEL_ONLY_RE.match(st):
            continue
        kept.append(s)

    cleaned = " ".join(kept).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # If stripping ate everything (the whole answer was just the link
    # footer), fall back to a short neutral line rather than returning blank.
    if not cleaned:
        cleaned = "Here's what you need for that step."

    return cleaned


def _build_messages(system: str, history: list[dict] | None,
                    question: str, context: str | None,
                    context_label: str = "Guide") -> list[dict]:
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history[-8:])
    if context:
        user_content = (
            f"Context from the {context_label}:\n{context}\n\n"
            f"{'─' * 40}\n\n"
            f"Question: {question}"
        )
    else:
        user_content = question
    messages.append({"role": "user", "content": user_content})
    return messages


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ASK FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def ask(client: OpenAI, question: str,
        history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """
    Route question → correct RAG pipeline → return (answer, sources).

    Intents:
      pms     → employee guide (pms_guide_chunks, steps 1-13)
      lm      → line manager guide (lm_guide_chunks, steps 1-12)
      general → direct LLM answer, no retrieval
    """
    sources: list[dict] = []
    ql = question.lower().strip()

    # ── Shortcut: bare video / link requests ─────────────────────────────
    if ql in _VIDEO_TRIGGERS or (
        len(ql.split()) <= 6
        and any(t in ql for t in ["video", "link", "tutorial", "drive"])
        and not any(kw in ql for kw in _KPI_KEYWORDS)
    ):
        answer = (
            "You'll find the video tutorial and supporting documents in the "
            "sidebar on the left — under **📹 Video Tutorial**.\n\n"
            "Let me know if you need help with any specific step!"
        )
        return answer, sources

    intent = _classify_intent(question)

    # ── General ───────────────────────────────────────────────────────────
    if intent == "general":
        messages = _build_messages(GENERAL_SYSTEM_PROMPT, history, question, context=None)
        return _call_llm(client, messages, max_tokens=_MAX_TOKENS["general"]), sources

    # ── Line Manager guide ────────────────────────────────────────────────
    if intent == "lm":
        try:
            context = build_full_lm_guide_context()
        except Exception:
            context = ""

        if not context:
            messages = _build_messages(
                LM_SYSTEM_PROMPT, history,
                question + "\n\n[No guide data available — run ingest_lm.py first.]",
                context=None,
            )
            raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["lm"], is_pms=True)
            answer, _ = _extract_steps_tag(raw_answer)
            return answer, sources

        messages = _build_messages(
            LM_SYSTEM_PROMPT, history, question, context=context,
            context_label="BP PMS Line Manager Guide (complete, all steps)",
        )
        raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["lm"], is_pms=True)
        answer, refs = _extract_steps_tag(raw_answer)

        # Safety net: force Login chunk if question mentions login/start
        ql_check = question.lower()
        wants_login = any(w in ql_check for w in [
            "login", "log in", "sign in", "logon",
            "shuru", "start se", "start sai", "ibtida",
        ])
        if wants_login and LOGIN_MARKER not in refs:
            refs = [LOGIN_MARKER] + refs

        try:
            sources = get_lm_chunks_by_refs(refs)
        except Exception:
            sources = []

        return answer, sources

    # ── PMS employee guide ────────────────────────────────────────────────
    if intent == "pms":
        try:
            context = build_full_guide_context()
        except Exception:
            context = ""

        if not context:
            messages = _build_messages(
                PMS_SYSTEM_PROMPT, history,
                question + "\n\n[No guide data available in database.]",
                context=None,
            )
            raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["pms"], is_pms=True)
            answer, _ = _extract_steps_tag(raw_answer)
            return answer, sources

        messages = _build_messages(
            PMS_SYSTEM_PROMPT, history, question, context=context,
            context_label="BP PMS Employee Guide (complete, all steps)",
        )
        raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["pms"], is_pms=True)
        answer, refs = _extract_steps_tag(raw_answer)

        ql_check = question.lower()
        wants_login = any(w in ql_check for w in [
            "login", "log in", "sign in", "logon",
            "shuru", "start se", "start sai", "ibtida",
        ])
        if wants_login and LOGIN_MARKER not in refs:
            refs = [LOGIN_MARKER] + refs

        try:
            sources = get_chunks_by_refs(refs)
        except Exception:
            sources = []

        return answer, sources

    # Fallback
    messages = _build_messages(GENERAL_SYSTEM_PROMPT, history, question, None)
    return _call_llm(client, messages, max_tokens=_MAX_TOKENS["general"]), sources


# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def make_fw_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=FIREWORKS_BASE_URL)


def chunk_count() -> int:
    """Return total chunks in pms_guide_chunks (both doc_source values)."""
    with _DBConn() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '5000'")  # 5s, ms units
            cur.execute("SELECT COUNT(*) FROM pms_guide_chunks")
            return cur.fetchone()[0]