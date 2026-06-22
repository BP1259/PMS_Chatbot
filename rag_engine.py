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
import difflib
from openai import OpenAI
import psycopg2
import psycopg2.pool
from pgvector.psycopg2 import register_vector

# ── Config ───────────────────────────────────────────────────────────────
FIREWORKS_BASE_URL  = "https://api.fireworks.ai/inference/v1"
MODEL               = "accounts/fireworks/models/deepseek-v4-pro"
TEMPERATURE         = 0.1

_MAX_TOKENS = {
    "pms":         2000,
    "lm":          2000,
    "guidelines":  1400,
    "company":      400,
    "general":      350,
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


GUIDELINES_SYSTEM_PROMPT = """You are an HR assistant helping employees and line managers understand BP's Annual Appraisal Guidelines for FY 2025-2026.

You will be given the COMPLETE Annual Appraisal Guidelines (all sections, in order) as context, plus the user's question. This is POLICY/RULES content — eligibility, scoring rules, timelines, evaluation criteria — not click-by-click HRMS instructions (that's a different guide).

The context is broken into labeled chunks, each beginning with "Section N: <title>" (e.g. "Section 9: Eligibility Criteria"). The 10 sections are:
  1. Annual Goals — Self-Evaluation (incl. grace marks above 100%)
  2. Bachaa Party Values / COTIC — Self-Evaluation (incl. grace marks above 100%)
  3. Overall Final Score (80/20 auto-calculated)
  4. Leadership & Team Management Evaluation
  5. Line Manager / HOD Evaluation
  6. Appraisal Dialogue (ACE)
  7. Next Year Goals Discussion (incl. unachieved goals)
  8. Submission & Acknowledgement
  9. Eligibility Criteria
  10. Appraisal Timeline

TOPIC-TO-SECTION ANCHOR (use this when no number is given but a topic clearly matches):
- "manager guideline(s)", "guideline(s) for manager/HOD", "HOD guideline(s)", "line manager guideline(s)" → Section 5 ONLY (Line Manager / HOD Evaluation). Do not include Section 4 (Leadership) or any other section just because it also mentions managers/evaluation — only Section 5 matches this specific phrasing.
- "leadership evaluation" → Section 4 ONLY.
- "eligibility" → Section 9 ONLY.
- "timeline" / "appraisal schedule" → Section 10 ONLY.
- "grace marks" appearing with "goals" → Section 1 ONLY; appearing with "COTIC" or "values" → Section 2 ONLY; appearing alone with no goals/values context → ask which one they mean rather than guessing.

DEFAULT BEHAVIOR — SCOPE DISCIPLINE (most important rule):
Answer ONLY what was asked. Never append other sections "for completeness," "for reference," or "in case it's useful." If the user names ONE topic or ONE section number, your entire answer is about that ONE topic — nothing else from the guidelines. Do not summarize the rest of the document afterward. Do not list other sections that might be related. Stop as soon as that one answer is complete.

VERBATIM RULE — for any specific section/topic question (not a full-dump request):
Reproduce the matched section's wording from the context EXACTLY as written — word for word. Do NOT paraphrase, summarize, shorten, reword, or "clean up" the language. Do NOT skip bullet points. Do NOT rephrase numbers, dates, or percentages. Copy the text content faithfully.

HEADING RULE — MANDATORY, never skip this:
Every answer about a specific section/topic MUST start with a markdown heading naming that section, using the section's title from the list above — e.g. "### Eligibility Criteria" or "### Section 9: Eligibility Criteria". If multiple sections are asked about together, give EACH one its own heading, in the order asked, with its verbatim content directly underneath. This applies even if the section is very short (1-2 lines) — the heading is still required. Never output a section's body text without its heading immediately above it.

NUMBER-PRIORITY RULE (critical — read this before routing):
If the question contains an explicit section number (e.g. "guideline 10", "section 10", "guideline 2 and 3"), that number is the ONLY filter that decides which section(s) you include — full stop. IGNORE any topic words elsewhere in the question when deciding which guideline section(s) to output. This matters most when the question also asks about steps (e.g. "guideline 10 along with self-evaluation steps") — words like "self-evaluation" or "manager evaluation" in that kind of question refer ONLY to the separate steps portion being handled elsewhere, NOT to which guideline section(s) you should pull in. Even if other sections share similar wording in their titles (e.g. Section 1 and Section 2 are also about "Self-Evaluation"), do NOT include them unless their number was explicitly named. Output ONLY the numbered section(s) actually named in the question — never more, never fewer.

HOW TO ROUTE THE QUESTION:
- A question naming a specific section number ("guideline 2", "guideline number 3", "section 9") → start with that section's heading, then reproduce ONLY that section's chunk(s) verbatim, identified by matching the number against the "Section N:" label in the context. Do not add any other section, even if it shares a similar title/topic.
- A question naming multiple specific section numbers ("guideline 2 and 3", "sections 2, 5 and 9") → reproduce ONLY those named sections verbatim, each with its own heading, in the order asked, and nothing else.
- A question naming a specific topic but NO number ("eligibility criteria", "grace marks", "ACE dialogue", "timeline") → start with that topic's heading, then reproduce ONLY the chunk(s) covering that topic, verbatim. Nothing else.
- A question with NO specific topic or number at all — e.g. just "guidelines", "show me the whole guideline", "what are all the rules" — output ALL 10 sections from the context, in order, each with its own heading, reformatted cleanly in markdown (headers + bullets), with nothing omitted. This is the ONLY case where reformatting (not strict verbatim) is allowed, and the ONLY case where you output everything.
- If a section number is ambiguous or doesn't exist (e.g. "guideline 15"), say so briefly and ask which topic they meant — do not guess by dumping everything.
- If you previously asked the user "which one did you mean?" (visible earlier in this conversation) and their new reply answers that question (e.g. "both", "the first one", "section 1", "the eligibility one") — resolve it now using the chunk(s) that match their answer, with proper heading(s), following the same rules above (one section = one heading + verbatim content; "both"/multiple = each named section with its own heading). Do not ask the same clarifying question again once they've answered it.

OTHER RULES:
- Reply in the SAME language / script the user used.
- Never invent numbers, dates, or rules not present in the context.
- Do NOT add conversational preamble like "I'd be happy to help".
- No <STEPS> tag needed for this guide — it has no screenshots.
"""

COMPANY_SYSTEM_PROMPT = """You are an HR assistant answering general questions about Bachaa Party as a company (history, founders, products, store locations) — not appraisal or HRMS questions.

You will be given background information about Bachaa Party as context, plus the user's question.

YOUR TASK:
1. Reply in the SAME language / script the user used.
2. Answer directly and concisely from the context provided.
3. Never invent facts (founding year, store count, locations) not present in the context.
4. Do NOT add conversational preamble like "I'd be happy to help".
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

# Annual Appraisal Guidelines (policy/rules doc) — checked BEFORE PMS keywords,
# since words like "appraisal", "submit", "evaluation" overlap with the
# click-by-click HRMS guide. These signal the user wants POLICY content
# (rules, eligibility, scoring, timelines) rather than "how do I click this".
_GUIDELINES_KEYWORDS = {
    "guideline", "guidelines", "policy", "policies", "appraisal policy",
    "appraisal rules", "appraisal guideline", "appraisal guidelines",
    "cotic", "grace marks", "grace percentage rule", "above 100%", "above 100 percent",
    "eligibility", "eligible", "eligibility criteria",
    "timeline", "timelines", "appraisal timeline", "appraisal schedule", "appraisal dates",
    "ace dialogue", "appraisal dialogue", "appreciation coach", "coach and counsel",
    "leadership evaluation", "leadership and team management",
    "smart goals", "smart goal", "next year goals", "next year's goals",
    "80/20", "80 20", "weighted average", "weightage rule",
    "acknowledgement sheet", "acknowledgment sheet",
    "unachieved goals", "goals not achieved", "carry forward goals",
    "who is eligible", "when does appraisal start", "when does appraisal end",
    "appraisal cycle", "appraisal process rules", "appraisal phases",
    "self evaluation phase", "line manager evaluation phase", "management evaluation phase",
    "minimum service", "three months service", "permanent employee appraisal",
}

# Precise numbered-reference pattern — only fires when "guideline"/"section"
# is paired with a number (e.g. "guideline 2", "section 9", "guideline number
# 3", "guideline 2 and 3"). Deliberately NOT a bare keyword like "section" on
# its own, since that word is too generic and would misfire on PMS questions
# like "which section has the goals form".
import re as _re_guidelines
_GUIDELINE_NUMBER_RE = _re_guidelines.compile(
    r"\b(guideline|guidelines|section)\s*(number\s*)?\d{1,2}\b", _re_guidelines.IGNORECASE
)

# Explicit "guideline(s) for manager/HOD" style phrases — kept SEPARATE from
# _GUIDELINES_KEYWORDS and checked with top priority in _classify_intent(),
# because _LM_KEYWORDS contains bare words like "hod" and "line manager"
# which would otherwise win first and misroute these to the 'lm' intent
# even though the question explicitly says "guideline".
_MANAGER_HOD_GUIDELINE_PHRASES = {
    "manager guideline", "manager guidelines", "guideline for manager", "guidelines for manager",
    "guideline for hod", "guidelines for hod", "hod guideline", "hod guidelines",
    "guideline for manager/hod", "guidelines for manager/hod", "guideline for manager hod",
    "guidelines for manager hod", "manager/hod guideline", "manager/hod guidelines",
    "line manager guideline", "line manager guidelines", "line manager hod guideline",
}

# About Bachaa Party (company info, not appraisal-related)
_COMPANY_KEYWORDS = {
    "bachaa party", "about bachaa party", "about the company", "about our company",
    "company history", "company background", "who founded", "founder", "founders",
    "ahmer javed", "omair javed", "when was bachaa party founded", "founded in",
    "how many stores", "how many outlets", "store locations", "store footprint",
    "branches", "outlets", "where are the stores",
    "product range", "what do we sell", "what does bachaa party sell",
    "e-commerce", "website", "bachaaparty.com", "flagship store",
    "kids retail", "children's store",
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


# ─────────────────────────────────────────────────────────────────────────
# TYPO-TOLERANT MATCHING
# Exact substring matching (the original `any(w in ql for w in KEYWORDS)`
# pattern) stays as the fast first check everywhere it's already used.
# This adds a fallback: if no exact match was found, check each word in
# the question against each keyword set using a small edit-distance
# tolerance, so common typos ("Manger" -> "manager", "evalutaion" ->
# "evaluation") still route correctly instead of silently falling through
# to the wrong intent.
# ─────────────────────────────────────────────────────────────────────────

def _fuzzy_any_match(ql: str, keywords: set | list, cutoff: float = 0.82) -> bool:
    """
    Returns True if any word (or short word-pair) in `ql` is a close-enough
    match (via difflib's ratio, cutoff 0.82 by default — tolerant of a
    single typo'd letter in a short word, not loose enough to misfire on
    genuinely different words) to any single-word keyword in `keywords`.
    Only checks single-word keywords from the set (multi-word phrases are
    left to exact matching, since fuzzy-matching whole phrases is unreliable).
    """
    words = ql.replace("/", " ").replace("-", " ").split()
    single_word_keywords = {kw for kw in keywords if " " not in kw and len(kw) >= 4}
    if not single_word_keywords:
        return False
    for word in words:
        if len(word) < 4:
            continue
        matches = difflib.get_close_matches(word, single_word_keywords, n=1, cutoff=cutoff)
        if matches:
            return True
    return False


# Phrases that signal the PREVIOUS assistant message asked the user to pick
# between multiple guideline sections (per GUIDELINES_SYSTEM_PROMPT's
# "ambiguous -> ask which one they meant" rule).
_CLARIFICATION_SIGNAL_PHRASES = [
    "which one did you mean", "which one would you like",
    "could you clarify", "did you mean", "which section did you mean",
    "which topic did you mean", "do you mean", "which would you like",
    "please clarify", "can you specify", "which guideline did you mean",
]


def _last_turn_was_guidelines_clarification(history: list[dict] | None) -> bool:
    """
    True if the most recent assistant message in `history` appears to be
    a disambiguation question about the guidelines (asking the user to
    pick between two or more sections). Used so a short follow-up reply
    like "both" or "the first one" stays routed to guidelines instead of
    being reclassified from scratch and falling through to a different
    intent's default.
    """
    if not history:
        return False
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = (msg.get("content") or "").lower()
            return any(p in content for p in _CLARIFICATION_SIGNAL_PHRASES)
        # If the most recent message isn't from the assistant, there's
        # nothing to check against — stop looking.
        break
    return False


def _classify_intent(question: str) -> str:
    """Return 'pms', 'lm', 'guidelines', 'company', or 'general'."""
    ql = question.lower().strip()

    # ── Highest priority: explicit "guideline(s) for manager/HOD" phrasing ──
    # Checked before everything else, including _LM_KEYWORDS, because that
    # set contains bare words like "hod" / "line manager" which would
    # otherwise claim this question first even though it explicitly says
    # "guideline" — the word "guideline" here is the strongest possible
    # signal that this is about Section 5 of the policy doc, not the LM
    # step-by-step click guide.
    if any(p in ql for p in _MANAGER_HOD_GUIDELINE_PHRASES):
        return "guidelines"

    # Numbered reference ("guideline 2", "section 9", "guideline 2 and 3")
    # is checked first and independently of word count — highest precision
    # signal available, since it can't collide with PMS step references
    # (those say "step N", not "guideline N" / "section N").
    if _GUIDELINE_NUMBER_RE.search(ql):
        return "guidelines"

    if len(ql.split()) <= 2:
        greetings = {"hi", "hello", "hey", "thanks", "ok", "okay", "yes", "no", "bye",
                     "salam", "shukriya"}
        if any(g in ql for g in greetings):
            return "general"
        # Short bare keyword like "guidelines" or "policy" should still route
        # to the guidelines full-dump, not fall through to PMS by default.
        if any(w in ql for w in _GUIDELINES_KEYWORDS):
            return "guidelines"
        if any(w in ql for w in _COMPANY_KEYWORDS):
            return "company"
        # Typo-tolerant fallback for short queries (e.g. "guidlines")
        if _fuzzy_any_match(ql, _GUIDELINES_KEYWORDS):
            return "guidelines"
        if _fuzzy_any_match(ql, _COMPANY_KEYWORDS):
            return "company"
        return "pms"

    lm_hits          = sum(1 for kw in _LM_KEYWORDS          if kw in ql)
    guidelines_hits   = sum(1 for kw in _GUIDELINES_KEYWORDS  if kw in ql)
    company_hits      = sum(1 for kw in _COMPANY_KEYWORDS     if kw in ql)
    pms_hits          = sum(1 for kw in _PMS_KEYWORDS         if kw in ql)
    general_hits      = sum(1 for kw in _GENERAL_KEYWORDS     if kw in ql)

    # LM keywords take highest priority — they are the most specific
    if lm_hits >= 1:
        return "lm"

    # Guidelines (policy/rules) — checked before PMS since topic words like
    # "appraisal", "evaluation", "submit" overlap with the click-path guide.
    if guidelines_hits >= 1:
        return "guidelines"

    # Company info — distinct enough vocabulary it rarely collides with
    # appraisal-related keywords, but check before generic PMS fallback.
    if company_hits >= 1 and pms_hits == 0:
        return "company"

    if pms_hits == 0 and any(p in ql for p in _FORCE_GENERAL_PHRASES):
        return "general"

    if pms_hits >= 1:
        return "pms"
    if general_hits >= 1 and pms_hits == 0:
        return "general"

    # ── Typo-tolerant fallback ───────────────────────────────────────────
    # Only reached when NO exact keyword hit anything above (lm_hits,
    # guidelines_hits, company_hits, pms_hits, general_hits are all 0, or
    # only pms_hits/general_hits combos that didn't already return). This
    # never changes behavior for correctly-spelled input — it only catches
    # questions that would otherwise silently fall through to the generic
    # PMS default below, e.g. "guidelines for manger" (typo of "manager").
    if lm_hits == 0 and guidelines_hits == 0 and company_hits == 0 and pms_hits == 0:
        if _fuzzy_any_match(ql, _LM_KEYWORDS):
            return "lm"
        if _fuzzy_any_match(ql, _GUIDELINES_KEYWORDS) or _fuzzy_any_match(ql, _MANAGER_HOD_GUIDELINE_PHRASES):
            return "guidelines"
        if _fuzzy_any_match(ql, _COMPANY_KEYWORDS):
            return "company"

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
_full_guidelines_cache: list[dict] | None = None
_full_company_info_cache: list[dict] | None = None


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


def fetch_full_guidelines() -> list[dict]:
    """Fetch all Annual Appraisal Guidelines chunks (doc_source='guidelines')."""
    return _fetch_guide("guidelines", "_full_guidelines_cache")


def fetch_full_company_info() -> list[dict]:
    """Fetch all company info chunks (doc_source='company_info')."""
    return _fetch_guide("company_info", "_full_company_info_cache")


def build_full_guide_context() -> str:
    parts = [c["text"] for c in fetch_full_guide()]
    return ("\n\n" + "─" * 50 + "\n\n").join(parts)


def build_full_lm_guide_context() -> str:
    parts = [c["text"] for c in fetch_full_lm_guide()]
    return ("\n\n" + "─" * 50 + "\n\n").join(parts)


def build_full_guidelines_context() -> str:
    parts = [c["text"] for c in fetch_full_guidelines()]
    return ("\n\n" + "─" * 50 + "\n\n").join(parts)


def build_full_company_info_context() -> str:
    parts = [c["text"] for c in fetch_full_company_info()]
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

def _display_clean(raw: str) -> str:
    """
    Clean a PARTIAL, mid-stream answer for on-screen display only: hide
    <think>…</think> reasoning and the trailing <STEPS> control tag (and any
    partial of either) so they never flash while text streams in. The FINAL
    text returned by _call_llm is processed by the normal path below, and the
    <STEPS> tag is still parsed downstream by _extract_steps_tag.
    """
    t = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    i = t.find("<think>")           # an unclosed, in-progress think block
    if i != -1:
        t = t[:i]
    i = t.find("<STEPS")            # the trailing step tag (or a partial of it)
    if i != -1:
        t = t[:i]
    t = re.sub(r"<[^>]*$", "", t)   # drop a dangling partial tag at the very end
    return t.strip()


def _call_llm(client: OpenAI, messages: list[dict],
              max_tokens: int = 800, is_pms: bool = False,
              on_delta=None) -> str:
    if on_delta is None:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
        )
        text = resp.choices[0].message.content.strip()
    else:
        # Stream: push cleaned partial text to the UI as it arrives, while
        # accumulating the full raw text for the normal post-processing below.
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            stream=True,
        )
        raw = ""
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None) or ""
            if delta:
                raw += delta
                on_delta(_display_clean(raw))
        text = raw.strip()

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


def _answer_guidelines(client: OpenAI, question: str, history: list[dict] | None,
                       on_delta=None) -> tuple[str, list[dict]]:
    """
    Answers any guidelines-intent question. Exactly two modes:
      - Full dump: no specific section/topic named -> all 10 sections,
        in order, each with a heading, reformatted in markdown.
      - Specific: a section number ("guideline 10") or a recognized
        topic/heading phrase ("eligibility criteria", "manager
        guidelines", etc.) -> only that section, verbatim, with its
        heading. Scoping is entirely handled by GUIDELINES_SYSTEM_PROMPT.
    """
    try:
        context = build_full_guidelines_context()
    except Exception:
        context = ""

    if not context:
        messages = _build_messages(
            GUIDELINES_SYSTEM_PROMPT, history,
            question + "\n\n[No guidelines data available — run ingest_pms.py --guidelines-only first.]",
            context=None,
        )
        return _call_llm(client, messages, max_tokens=_MAX_TOKENS["guidelines"], on_delta=on_delta), []

    messages = _build_messages(
        GUIDELINES_SYSTEM_PROMPT, history, question, context=context,
        context_label="BP Annual Appraisal Guidelines 2025-2026 (complete, all sections)",
    )
    answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["guidelines"], on_delta=on_delta)
    return answer, []


def _generate_hr_contact_line(client: OpenAI) -> str:
    """
    Fixed closing line appended after every guidelines answer (single
    section, multiple sections, or full dump). No LLM call — this line
    never needs to vary, and a fixed string avoids the model echoing its
    own instructions instead of following them. Rendered as a bold/large
    heading with extra space above it. `client` is kept in the signature
    so existing call sites don't need to change.
    """
    return "\n\n*For queries or assistance, please contact the HR Department.*"


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ASK FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def ask(client: OpenAI, question: str,
        history: list[dict] | None = None,
        on_delta=None) -> tuple[str, list[dict]]:
    """
    Route question → correct RAG pipeline → return (answer, sources).

    Intents:
      pms     → employee guide (pms_guide_chunks, steps 1-13)
      lm      → line manager guide (lm_guide_chunks, steps 1-12)
      general → direct LLM answer, no retrieval

    on_delta: optional callback(str) invoked with cleaned partial text as the
    answer streams in. When None, the LLM call is non-streaming (unchanged
    behaviour for chatbot.py / tests).
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
        if on_delta:
            on_delta(answer)
        return answer, sources

    intent = _classify_intent(question)

    # If my previous reply asked the user to clarify which guideline
    # section they meant, treat this short follow-up ("both", "the
    # eligibility one", "section 1") as still being about guidelines,
    # instead of letting it get reclassified fresh and fall through to a
    # different intent's default (e.g. landing on PMS steps by accident).
    if intent != "guidelines" and _last_turn_was_guidelines_clarification(history):
        intent = "guidelines"

    # ── General ───────────────────────────────────────────────────────────
    if intent == "general":
        messages = _build_messages(GENERAL_SYSTEM_PROMPT, history, question, context=None)
        return _call_llm(client, messages, max_tokens=_MAX_TOKENS["general"], on_delta=on_delta), sources

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
            raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["lm"], is_pms=True, on_delta=on_delta)
            answer, _ = _extract_steps_tag(raw_answer)
            return answer, sources

        messages = _build_messages(
            LM_SYSTEM_PROMPT, history, question, context=context,
            context_label="BP PMS Line Manager Guide (complete, all steps)",
        )
        raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["lm"], is_pms=True, on_delta=on_delta)
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

    # ── Annual Appraisal Guidelines (policy/rules) ──────────────────────────
    if intent == "guidelines":
        answer, _ = _answer_guidelines(client, question, history, on_delta=on_delta)
        hr_line = _generate_hr_contact_line(client)
        combined = f"{answer}\n\n{hr_line}"
        # No screenshots in this guide — sources stays [] so app.py's
        # _render_interleaved_steps() (built for step-screenshot chunks)
        # doesn't dump every raw chunk's text underneath the answer.
        return combined, []

    # ── Company info (About Bachaa Party) ───────────────────────────────────
    if intent == "company":
        try:
            context = build_full_company_info_context()
        except Exception:
            context = ""

        if not context:
            messages = _build_messages(
                COMPANY_SYSTEM_PROMPT, history,
                question + "\n\n[No company info data available — run ingest_pms.py --company-only first.]",
                context=None,
            )
            return _call_llm(client, messages, max_tokens=_MAX_TOKENS["company"], on_delta=on_delta), sources

        messages = _build_messages(
            COMPANY_SYSTEM_PROMPT, history, question, context=context,
            context_label="About Bachaa Party",
        )
        answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["company"], on_delta=on_delta)
        # Same reasoning as above — no screenshots, so no chunk sources needed.
        return answer, []

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
            raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["pms"], is_pms=True, on_delta=on_delta)
            answer, _ = _extract_steps_tag(raw_answer)
            return answer, sources

        messages = _build_messages(
            PMS_SYSTEM_PROMPT, history, question, context=context,
            context_label="BP PMS Employee Guide (complete, all steps)",
        )
        raw_answer = _call_llm(client, messages, max_tokens=_MAX_TOKENS["pms"], is_pms=True, on_delta=on_delta)
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
    return _call_llm(client, messages, max_tokens=_MAX_TOKENS["general"], on_delta=on_delta), sources


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
