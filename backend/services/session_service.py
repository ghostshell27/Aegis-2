"""Session orchestration: hook, explain, exercise, consequence, Socratic help.

This module owns the teaching flow. Every turn sends the AI:

* a system prompt that bakes in the Socratic rules, LaTeX formatting, and
  the consequence-scenario rubric;
* the curriculum metadata for the current topic;
* a compact profile summary so difficulty adapts;
* the prior conversation (loaded from the ``messages`` table) so the AI can
  continue a running scenario.

The AI is asked to emit a strict JSON envelope. That envelope contains the
assistant's natural-language reply *and* structured fields (``outcome``,
``exercise_active``, ``mastery_delta``, ``error_tag``) that the backend uses
to update progress deterministically -- no scraping of prose.
"""
from __future__ import annotations

import json
from typing import Any

from backend import ai_wrapper
from backend.database import db
from backend.services.curriculum_service import curriculum
from backend.services import user_profile


SYSTEM_RULES = """You are Aegis, an AI mathematics tutor inside a desktop app
built for adaptive algebra and calculus learning. You must obey these rules
on every turn without exception.

1. Formatting. Write every mathematical expression in LaTeX. Use $...$ for
   inline math and $$...$$ for display math. Always use real backslashes
   for LaTeX commands -- write \\sqrt{2}, \\frac{a}{b}, \\pi, \\mathbb{R},
   \\quad, \\ldots, \\overline{x}, \\int, \\sum, etc. Never write "sqrt2"
   or "frac{a}{b}" without the backslash; those will not render.
   Never use plain-text pseudo-math like x^2 outside of a LaTeX block.
   Keep prose concise and visually clean with short paragraphs and
   occasional bullet lists.

2. Teaching flow. A topic session advances through phases in this order:
   HOOK -> TEACH -> WORKED_EXAMPLE -> EXERCISE_1 -> EXERCISE_2 -> CHALLENGE
   -> COMPLETE. Use the phase field you receive to decide what to produce
   next. Never skip a phase. If the learner asks for a simpler restatement
   or for an example, stay in the current phase and produce that.

3. Hook. Begin every topic with a vivid, concrete real-world scenario in
   the requested domain that motivates why this topic matters. Name a
   specific setting, a named stakeholder, numbers where possible. This
   scenario will be reused throughout the session.

4. Consequences. When the learner answers an exercise incorrectly, do NOT
   say "try again." Continue the live scenario and narrate what would
   happen in that context using the wrong numbers the learner gave. Be
   specific, physical, and brief. Then begin a step-by-step guided
   rederivation: ask the learner to supply each step, one small question at
   a time, correcting gently.

5. Don't-know mode. When action == "dont_know", run a Socratic walkthrough:
   ask the smallest possible first question that moves toward a solution,
   wait for an answer, confirm or correct, ask the next smallest question.
   After completing the walkthrough, produce a near-identical fresh
   problem so the learner can demonstrate the skill independently.

6. Adaptation. Use the provided learner profile to tune difficulty,
   scaffolding, and domain. A high-mastery learner gets harder variants and
   fewer hints. A struggling learner gets reinforcement of prerequisites
   before advancing.

7. Output shape. You MUST emit your reply as TWO sections separated by a
   sentinel line containing exactly ===MESSAGE===. The first section is a
   single line of compact JSON metadata; the second is the learner-facing
   markdown body. Example:

     {"phase":"EXERCISE_1","exercise_active":true,"outcome":"ongoing","mastery_delta":0,"suggestions":["Give me a hint","Simpler please"],"domain_used":"computer_graphics","error_tag":null,"next_hint":"Start by simplifying \\sqrt{9}."}
     ===MESSAGE===
     ## Exercise 1 -- Sofia's Coordinates

     Sofia needs to place a sprite at $x = \\sqrt{9}$. Classify it...

   Allowed JSON fields:
     phase: HOOK | TEACH | WORKED_EXAMPLE | EXERCISE_1 | EXERCISE_2 |
            CHALLENGE | COMPLETE | CONSEQUENCE | SOCRATIC | RECAP
     exercise_active: true when waiting for a numeric/symbolic answer
     outcome: ongoing | correct | incorrect | complete
     mastery_delta: integer in [-10, +15]
     suggestions: array of 0-4 short follow-up button labels
     domain_used: string (e.g. computer_graphics, structural_engineering)
     error_tag: short snake_case tag when outcome is incorrect, else null
     next_hint: optional one-sentence nudge or null

   The JSON line must be valid (escape backslashes inside strings as \\\\).
   The body after ===MESSAGE=== is RAW markdown -- do NOT escape backslashes
   in math, do NOT wrap in code fences, do NOT add anything after the body.
   This is the only place where LaTeX should appear with single backslashes.
"""


def _ai_messages_from_rows(rows: list[dict]) -> list[dict[str, str]]:
    """Convert stored ``messages`` rows into the AI wire format.

    Internal framing messages (SESSION_START prompts and similar) are skipped
    so they don't get replayed to the model on every turn.
    """
    out: list[dict[str, str]] = []
    for row in rows:
        role = row["role"]
        if role not in ("user", "assistant"):
            continue
        if _safe_json(row.get("meta")).get("internal"):
            continue
        out.append({"role": role, "content": row["content"]})
    return out


async def _profile_snippet() -> str:
    summary = await user_profile.get_summary()
    return json.dumps(summary, ensure_ascii=False)


async def _topic_snippet(topic_id: str) -> str:
    topic = curriculum.topic(topic_id)
    if not topic:
        return json.dumps({"error": "unknown topic"})
    history = await user_profile.get_topic_history(topic_id)
    snippet = {
        "topic": {
            "id": topic["id"],
            "title": topic["title"],
            "difficulty": topic["difficulty"],
            "prerequisites": topic["prerequisites"],
            "objectives": topic["objectives"],
            "domain_affinity": topic.get("domain_affinity", []),
            "track": topic["track_id"],
            "unit": topic["unit_id"],
        },
        "history": history,
    }
    return json.dumps(snippet, ensure_ascii=False)


async def _append_message(
    session_id: int, role: str, content: str, meta: dict[str, Any] | None = None
) -> None:
    await db.execute(
        "INSERT INTO messages(session_id, role, content, meta) VALUES (?, ?, ?, ?)",
        (session_id, role, content, json.dumps(meta or {})),
    )


def _estimate_tokens(text: str) -> int:
    """Cheap token estimate: ~4 chars/token (close enough for the meter)."""
    return max(1, len(text) // 4)


# A reasonably comprehensive list of LaTeX commands that frequently lose
# their leading backslash when models emit malformed JSON. We use this to
# repair messages post-parse so KaTeX can render them.
_LATEX_COMMANDS = frozenset((
    # roots / fractions / binomials
    "sqrt", "frac", "dfrac", "tfrac", "binom", "dbinom", "tbinom",
    # operators
    "sum", "prod", "int", "iint", "iiint", "oint", "lim", "limsup", "liminf",
    "sup", "inf", "max", "min", "arg", "log", "ln", "lg", "exp",
    "sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "deg", "det", "dim", "ker", "gcd", "mod",
    # greek
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta",
    "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi",
    "omicron", "pi", "varpi", "rho", "varrho", "sigma", "varsigma", "tau",
    "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega",
    # blackboard / cal / frak / bf / it / rm / sf / tt / scr / bbm
    "mathbb", "mathbf", "mathit", "mathrm", "mathcal", "mathfrak",
    "mathsf", "mathtt", "mathscr", "boldsymbol",
    # text + decorations
    "text", "textit", "textbf", "textrm", "textsf", "texttt",
    "overline", "underline", "overrightarrow", "overleftarrow",
    "widehat", "widetilde", "hat", "tilde", "bar", "vec", "dot", "ddot",
    # spacing
    "quad", "qquad", "thinspace", "negthinspace", "medspace", "negmedspace",
    "thickspace", "negthickspace",
    # ellipses / dots
    "ldots", "cdots", "vdots", "ddots", "dotsb", "dotsc", "dotsi", "dotsm",
    # relations
    "leq", "geq", "neq", "ne", "le", "ge", "approx", "sim", "simeq",
    "equiv", "propto", "cong", "subset", "supset", "subseteq", "supseteq",
    "in", "notin", "ni", "cup", "cap", "setminus", "emptyset", "varnothing",
    # arrows
    "to", "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
    "leftrightarrow", "Leftrightarrow", "longrightarrow", "longleftarrow",
    "mapsto", "implies", "iff",
    # binary operators
    "cdot", "times", "div", "pm", "mp", "ast", "star", "circ", "bullet",
    "oplus", "ominus", "otimes", "oslash", "odot",
    # qualifiers / quantifiers
    "infty", "partial", "nabla", "forall", "exists", "neg", "lnot", "lor",
    "land", "lnot",
    # delimiters
    "left", "right", "big", "Big", "bigg", "Bigg",
    "lfloor", "rfloor", "lceil", "rceil", "langle", "rangle",
    # matrix / array helpers (the env names)
    "begin", "end",
    # misc
    "boxed", "color", "textcolor", "phantom", "hphantom", "vphantom",
    "stackrel", "underset", "overset",
))


def _repair_latex_in_math(message: str) -> str:
    """If the AI dropped backslashes inside ``$...$`` or ``$$...$$`` blocks,
    add them back for known LaTeX commands so KaTeX can render the math.

    A purely textual heuristic: walk the string, track whether we're inside
    a math delimiter, and prepend ``\\`` to alphabetic runs that match a
    known command and aren't already preceded by a backslash.
    """
    if not message or "$" not in message:
        return message
    out: list[str] = []
    i = 0
    n = len(message)
    inline = False
    display = False
    while i < n:
        ch = message[i]
        # Toggle display math first ($$...$$).
        if ch == "$" and i + 1 < n and message[i + 1] == "$":
            display = not display
            out.append("$$")
            i += 2
            continue
        if ch == "$" and not display:
            inline = not inline
            out.append("$")
            i += 1
            continue
        if (inline or display) and ch.isalpha():
            j = i
            while j < n and message[j].isalpha():
                j += 1
            word = message[i:j]
            preceded_by_bs = i > 0 and message[i - 1] == "\\"
            if not preceded_by_bs and word in _LATEX_COMMANDS:
                out.append("\\")
                out.append(word)
            else:
                out.append(word)
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


async def session_context_usage(session_id: int) -> dict[str, int]:
    """Return an approximate token count for everything we'd send the model
    on the next turn (system rules + persisted messages). Used to drive the
    in-UI context-usage bar."""
    rows = await _load_messages(session_id)
    total = _estimate_tokens(SYSTEM_RULES)
    for r in rows:
        if _safe_json(r.get("meta")).get("internal"):
            continue
        total += _estimate_tokens(r.get("content") or "")
    return {"tokens_estimate": total}


async def _load_messages(session_id: int) -> list[dict]:
    return await db.fetch_all(
        "SELECT id, role, content, meta FROM messages WHERE session_id = ? "
        "ORDER BY id ASC",
        (session_id,),
    )


async def _last_summary(topic_id: str) -> str:
    row = await db.fetch_one(
        "SELECT last_summary FROM topic_progress WHERE topic_id = ?", (topic_id,)
    )
    return (row or {}).get("last_summary", "") if row else ""


async def start_session(
    topic_id: str, mode: str = "learn", domain_hint: str | None = None
) -> dict[str, Any]:
    topic = curriculum.topic(topic_id)
    if not topic:
        raise ValueError(f"Unknown topic: {topic_id}")

    domain = domain_hint or await user_profile.best_domain(
        default=(topic.get("domain_affinity") or ["structural_engineering"])[0]
    )

    session_id = await db.execute(
        "INSERT INTO sessions(topic_id, track_id, domain, mode) VALUES (?, ?, ?, ?)",
        (topic_id, topic["track_id"], domain, mode),
    )

    await db.execute(
        "INSERT INTO topic_progress(topic_id, track_id, unit_id, status, last_session_id) "
        "VALUES (?, ?, ?, 'in_progress', ?) "
        "ON CONFLICT(topic_id) DO UPDATE SET "
        "status = CASE WHEN topic_progress.status = 'mastered' THEN 'mastered' "
        "ELSE 'in_progress' END, last_session_id = excluded.last_session_id, "
        "updated_at = datetime('now')",
        (topic_id, topic["track_id"], topic["unit_id"], session_id),
    )

    await user_profile.bump_domain_stat(domain)

    profile_json = await _profile_snippet()
    topic_json = await _topic_snippet(topic_id)
    last_summary = await _last_summary(topic_id)
    is_capstone = curriculum.is_capstone(topic_id)

    user_prompt = (
        f"SESSION_START\n"
        f"mode={mode}\n"
        f"phase={'CAPSTONE_KICKOFF' if is_capstone else 'HOOK'}\n"
        f"requested_domain={domain}\n"
        f"profile={profile_json}\n"
        f"topic={topic_json}\n"
        f"prior_session_summary={json.dumps(last_summary)}\n\n"
        "Begin the topic. If mode == 'learn' and phase == HOOK, produce a "
        "vivid real-world scenario and then the first teaching block. "
        "If this is a capstone, introduce the full project and the first "
        "phase of work; do not provide solutions. "
        "Remember to return only the JSON envelope."
    )

    envelope = await _chat_and_parse(
        system_prompt=SYSTEM_RULES,
        ai_messages=[{"role": "user", "content": user_prompt}],
    )

    await _append_message(session_id, "user", user_prompt, {"internal": True})
    await _append_message(
        session_id, "assistant", envelope["assistant_message"],
        {"phase": envelope.get("phase"), "raw": envelope},
    )

    usage = await session_context_usage(session_id)
    return {
        "session_id": session_id,
        "assistant_message": envelope["assistant_message"],
        "suggestions": envelope.get("suggestions", []),
        "exercise_active": bool(envelope.get("exercise_active")),
        "outcome": envelope.get("outcome", "ongoing"),
        "mastery_delta": int(envelope.get("mastery_delta") or 0),
        "metadata": {
            "phase": envelope.get("phase"),
            "domain_used": envelope.get("domain_used", domain),
            "next_hint": envelope.get("next_hint"),
            "mode": mode,
            "topic": topic,
            "tokens_estimate": usage["tokens_estimate"],
        },
    }


async def handle_turn(
    session_id: int, user_content: str, action: str = "answer"
) -> dict[str, Any]:
    session = await db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not session:
        raise ValueError(f"Unknown session_id={session_id}")

    topic_id = session["topic_id"]
    topic = curriculum.topic(topic_id) or {}
    prior = await _load_messages(session_id)
    ai_msgs = _ai_messages_from_rows(prior)

    # The most recent assistant message in `prior` is the question/prompt the
    # learner is actually responding to. Capture it now before we append the
    # new turns so we can store it alongside the exercise attempt.
    prior_assistant_text = ""
    for row in reversed(prior):
        if row["role"] == "assistant":
            prior_assistant_text = (row.get("content") or "")[:2000]
            break

    profile_json = await _profile_snippet()
    topic_json = await _topic_snippet(topic_id)

    framed_user = (
        f"LEARNER_TURN\n"
        f"action={action}\n"
        f"profile={profile_json}\n"
        f"topic={topic_json}\n"
        f"session_domain={session.get('domain')}\n"
        f"mode={session.get('mode')}\n\n"
        f"Learner message:\n{user_content}\n\n"
        "Continue teaching. Respect the action:\n"
        "- answer: treat the learner's text as a proposed answer to the most recent "
        "  exercise or question. Grade it and respond per the rules.\n"
        "- continue: advance to the next phase or block.\n"
        "- simpler: restate the most recent explanation more gently, then offer to proceed.\n"
        "- example: give a fresh worked example in the current phase.\n"
        "- hint: give the smallest possible nudge without revealing the answer.\n"
        "- dont_know: enter SOCRATIC mode; ask the next smallest question.\n\n"
        "Return ONLY the JSON envelope."
    )

    ai_msgs.append({"role": "user", "content": framed_user})

    envelope = await _chat_and_parse(
        system_prompt=SYSTEM_RULES,
        ai_messages=ai_msgs,
    )

    await _append_message(session_id, "user", user_content, {"action": action})
    await _append_message(
        session_id, "assistant", envelope["assistant_message"],
        {"phase": envelope.get("phase"), "raw": envelope},
    )

    outcome = envelope.get("outcome", "ongoing")
    mastery_delta = int(envelope.get("mastery_delta") or 0)
    error_tag = envelope.get("error_tag")

    await _update_progress(
        topic_id=topic_id,
        track_id=session["track_id"],
        unit_id=topic.get("unit_id", ""),
        outcome=outcome,
        mastery_delta=mastery_delta,
        error_tag=error_tag,
        session_id=session_id,
        action=action,
        user_content=user_content,
        prompt_text=prior_assistant_text,
    )

    if outcome == "complete":
        await _finalize_session(session_id, envelope)

    usage = await session_context_usage(session_id)
    return {
        "session_id": session_id,
        "assistant_message": envelope["assistant_message"],
        "suggestions": envelope.get("suggestions", []),
        "exercise_active": bool(envelope.get("exercise_active")),
        "outcome": outcome,
        "mastery_delta": mastery_delta,
        "metadata": {
            "phase": envelope.get("phase"),
            "domain_used": envelope.get("domain_used", session.get("domain")),
            "next_hint": envelope.get("next_hint"),
            "error_tag": error_tag,
            "tokens_estimate": usage["tokens_estimate"],
        },
    }


async def end_session(session_id: int, outcome: str = "complete") -> None:
    session = await db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not session:
        return

    # "checkpoint" means "save my place, I want to come back later" -- do not
    # terminate the session and skip the (slow, paid) AI summary call.
    if outcome == "checkpoint":
        await db.execute(
            "UPDATE sessions SET outcome = ? WHERE id = ?",
            (outcome, session_id),
        )
        return

    if session.get("ended_at"):
        # Already finalized; just refresh the outcome if it changed.
        if outcome and outcome != session.get("outcome"):
            await db.execute(
                "UPDATE sessions SET outcome = ? WHERE id = ?",
                (outcome, session_id),
            )
        return

    summary = await _summarize_session(session_id)
    await db.execute(
        "UPDATE sessions SET ended_at = datetime('now'), outcome = ?, summary = ? "
        "WHERE id = ?",
        (outcome, summary, session_id),
    )
    if summary:
        await db.execute(
            "UPDATE topic_progress SET last_summary = ?, updated_at = datetime('now') "
            "WHERE topic_id = ?",
            (summary, session["topic_id"]),
        )


async def load_history(session_id: int) -> list[dict[str, Any]]:
    rows = await _load_messages(session_id)
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = _safe_json(r.get("meta"))
        if meta.get("internal"):
            continue
        out.append({
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "meta": meta,
        })
    return out


def _safe_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def _update_progress(
    *,
    topic_id: str,
    track_id: str,
    unit_id: str,
    outcome: str,
    mastery_delta: int,
    error_tag: str | None,
    session_id: int,
    action: str,
    user_content: str,
    prompt_text: str = "",
) -> None:
    row = await db.fetch_one(
        "SELECT mastery_score, attempts, correct, error_patterns, status "
        "FROM topic_progress WHERE topic_id = ?",
        (topic_id,),
    )
    mastery = int((row or {}).get("mastery_score") or 0)
    attempts = int((row or {}).get("attempts") or 0)
    correct = int((row or {}).get("correct") or 0)
    status = (row or {}).get("status") or "in_progress"
    try:
        patterns = json.loads((row or {}).get("error_patterns") or "{}")
    except json.JSONDecodeError:
        patterns = {}

    is_exercise_answer = action == "answer" and outcome in ("correct", "incorrect")

    if is_exercise_answer:
        attempts += 1
        await db.execute(
            "INSERT INTO exercise_attempts(session_id, topic_id, prompt, user_answer, "
            "correct, concept_tag) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                topic_id,
                prompt_text,
                user_content,
                1 if outcome == "correct" else 0,
                error_tag,
            ),
        )
    if outcome == "correct":
        correct += 1
    if outcome == "incorrect" and error_tag:
        patterns[error_tag] = int(patterns.get(error_tag, 0)) + 1

    mastery = max(0, min(100, mastery + mastery_delta))
    # Unified mastery threshold: matches get_summary() so topic-map dots and
    # home tallies stay consistent.
    if mastery >= 80:
        status = "mastered"
    elif outcome == "complete":
        status = "mastered" if mastery >= 70 else "completed"
    elif status == "not_started":
        status = "in_progress"

    await db.execute(
        "INSERT INTO topic_progress(topic_id, track_id, unit_id, status, mastery_score, "
        "attempts, correct, error_patterns, last_session_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(topic_id) DO UPDATE SET "
        "status = excluded.status, mastery_score = excluded.mastery_score, "
        "attempts = excluded.attempts, correct = excluded.correct, "
        "error_patterns = excluded.error_patterns, last_session_id = excluded.last_session_id, "
        "updated_at = excluded.updated_at",
        (
            topic_id,
            track_id,
            unit_id,
            status,
            mastery,
            attempts,
            correct,
            json.dumps(patterns),
            session_id,
        ),
    )


async def _summarize_session(session_id: int) -> str:
    """Ask the AI for a short plain-text summary of this session to reload later."""
    rows = await _load_messages(session_id)
    convo = "\n".join(
        f"{r['role'].upper()}: {r['content'][:600]}"
        for r in rows
        if not _safe_json(r.get("meta")).get("internal")
    )[:8000]
    prompt = (
        "Summarize the following tutoring session in 4-6 sentences for future "
        "reload context. Focus on: which scenario/domain was used, which concepts "
        "the learner mastered or struggled with, and where the session left off. "
        "Plain prose, no JSON, no LaTeX.\n\nSESSION:\n" + convo
    )
    try:
        text = await ai_wrapper.chat(
            system_prompt="You are a concise assistant that summarizes tutoring sessions.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )
    except Exception:
        return ""
    return text.strip()


async def _finalize_session(session_id: int, envelope: dict[str, Any]) -> None:
    await end_session(session_id, outcome="complete")


_MESSAGE_SENTINEL = "===MESSAGE==="


def _parse_envelope(raw: str) -> dict[str, Any] | None:
    """Parse the new ``{json metadata}\\n===MESSAGE===\\nbody`` protocol.

    Returns ``None`` if the sentinel is missing so the caller can fall back
    to legacy single-JSON parsing.
    """
    if not raw or _MESSAGE_SENTINEL not in raw:
        return None
    head, _, body = raw.partition(_MESSAGE_SENTINEL)
    body = body.lstrip("\r\n")
    # The metadata section may have leading/trailing whitespace, code fences,
    # or be missing entirely.
    head = head.strip()
    if head.startswith("```"):
        head = head.strip("`")
        if head.lower().startswith("json"):
            head = head[4:]
        head = head.strip()
    start = head.find("{")
    end = head.rfind("}")
    meta: dict[str, Any] = {}
    if start != -1 and end != -1:
        try:
            parsed = json.loads(head[start : end + 1])
            if isinstance(parsed, dict):
                meta = parsed
        except json.JSONDecodeError:
            meta = {}
    meta["assistant_message"] = _repair_latex_in_math(body.rstrip())
    return meta


async def _chat_and_parse(
    system_prompt: str, ai_messages: list[dict[str, str]]
) -> dict[str, Any]:
    raw = await ai_wrapper.chat(
        system_prompt=system_prompt,
        messages=ai_messages,
        response_format="text",
        temperature=0.4,
        max_tokens=2400,
    )

    # New protocol: metadata JSON, sentinel, raw markdown body.
    data = _parse_envelope(raw)
    # Legacy fallback: a single JSON object that includes assistant_message.
    if data is None:
        data = await ai_wrapper.parse_json_response(raw)
        if data:
            data["assistant_message"] = _repair_latex_in_math(
                str(data.get("assistant_message", ""))
            )

    if not data or "assistant_message" not in data:
        # Last-resort fallback so the user never sees a crash.
        return {
            "phase": "TEACH",
            "assistant_message": raw or "(No response from the AI. Please retry.)",
            "suggestions": ["Continue", "Simpler, please", "Give me an example"],
            "exercise_active": False,
            "outcome": "ongoing",
            "mastery_delta": 0,
            "error_tag": None,
            "domain_used": "",
            "next_hint": None,
        }
    data.setdefault("suggestions", [])
    data.setdefault("exercise_active", False)
    data.setdefault("outcome", "ongoing")
    data.setdefault("mastery_delta", 0)
    data.setdefault("error_tag", None)
    data.setdefault("domain_used", "")
    data.setdefault("next_hint", None)
    return data
