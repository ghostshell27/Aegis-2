"""User profile aggregation.

Builds the compact context blob the AI sees before every turn so that
difficulty, pacing, and explanation depth can adapt.
"""
from __future__ import annotations

import json
from typing import Any

from backend.database import db


async def ensure_profile() -> dict[str, Any]:
    row = await db.fetch_one("SELECT * FROM user_profile WHERE id = 1")
    if row:
        return row
    await db.execute(
        "INSERT INTO user_profile(id, display_name, preferred_style, preferred_domain) "
        "VALUES (1, 'Learner', 'balanced', NULL)"
    )
    row = await db.fetch_one("SELECT * FROM user_profile WHERE id = 1")
    return row or {}


async def get_summary() -> dict[str, Any]:
    profile = await ensure_profile()
    progress_rows = await db.fetch_all(
        "SELECT topic_id, track_id, status, mastery_score, attempts, correct, "
        "time_seconds, error_patterns FROM topic_progress"
    )
    totals = {
        "topics_started": 0,
        "topics_mastered": 0,
        "total_attempts": 0,
        "total_correct": 0,
    }
    error_tally: dict[str, int] = {}
    for row in progress_rows:
        totals["total_attempts"] += row["attempts"] or 0
        totals["total_correct"] += row["correct"] or 0
        status = row["status"]
        if status != "not_started":
            totals["topics_started"] += 1
        if status == "mastered" or (row["mastery_score"] or 0) >= 80:
            totals["topics_mastered"] += 1
        try:
            patterns = json.loads(row["error_patterns"] or "{}")
        except json.JSONDecodeError:
            patterns = {}
        for tag, count in patterns.items():
            error_tally[tag] = error_tally.get(tag, 0) + int(count)
    top_errors = sorted(error_tally.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "display_name": profile.get("display_name", "Learner"),
        "preferred_style": profile.get("preferred_style", "balanced"),
        "preferred_domain": profile.get("preferred_domain"),
        "total_seconds": profile.get("total_seconds", 0),
        "totals": totals,
        "top_error_patterns": [{"tag": t, "count": c} for t, c in top_errors],
    }


async def get_topic_history(topic_id: str) -> dict[str, Any]:
    row = await db.fetch_one(
        "SELECT * FROM topic_progress WHERE topic_id = ?", (topic_id,)
    )
    if not row:
        return {
            "topic_id": topic_id,
            "status": "not_started",
            "mastery_score": 0,
            "attempts": 0,
            "correct": 0,
            "time_seconds": 0,
            "last_summary": "",
            "error_patterns": {},
        }
    try:
        patterns = json.loads(row["error_patterns"] or "{}")
    except json.JSONDecodeError:
        patterns = {}
    return {
        "topic_id": topic_id,
        "status": row["status"],
        "mastery_score": row["mastery_score"] or 0,
        "attempts": row["attempts"] or 0,
        "correct": row["correct"] or 0,
        "time_seconds": row["time_seconds"] or 0,
        "last_summary": row["last_summary"] or "",
        "error_patterns": patterns,
    }


async def set_preferred_domain(domain: str) -> None:
    await ensure_profile()
    await db.execute(
        "UPDATE user_profile SET preferred_domain = ?, updated_at = datetime('now') "
        "WHERE id = 1",
        (domain,),
    )


async def bump_domain_stat(domain: str, delta: int = 1) -> None:
    row = await db.fetch_one(
        "SELECT sessions_used, engagement_score FROM domain_stats WHERE domain = ?",
        (domain,),
    )
    if row:
        await db.execute(
            "UPDATE domain_stats SET sessions_used = sessions_used + 1, "
            "engagement_score = engagement_score + ?, updated_at = datetime('now') "
            "WHERE domain = ?",
            (delta, domain),
        )
    else:
        await db.execute(
            "INSERT INTO domain_stats(domain, sessions_used, engagement_score) "
            "VALUES (?, 1, ?)",
            (domain, delta),
        )


async def best_domain(default: str = "structural_engineering") -> str:
    profile = await ensure_profile()
    if profile.get("preferred_domain"):
        return profile["preferred_domain"]
    rows = await db.fetch_all(
        "SELECT domain, engagement_score FROM domain_stats "
        "ORDER BY engagement_score DESC LIMIT 1"
    )
    if rows:
        return rows[0]["domain"]
    return default
