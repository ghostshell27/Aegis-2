"""/api/progress -- topic progress map + capstone checkpoint state."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import db
from backend.services import user_profile
from backend.services.curriculum_service import curriculum
from backend.models import CapstoneState


router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/map")
async def progress_map() -> dict:
    rows = await db.fetch_all(
        "SELECT topic_id, track_id, status, mastery_score, attempts, correct, "
        "time_seconds FROM topic_progress"
    )
    by_topic = {r["topic_id"]: r for r in rows}
    tracks_out = []
    for track in curriculum.all().get("tracks", []):
        units_out = []
        for unit in track.get("units", []):
            topics_out = []
            for topic in unit.get("topics", []):
                p = by_topic.get(topic["id"]) or {}
                topics_out.append({
                    "id": topic["id"],
                    "title": topic["title"],
                    "difficulty": topic.get("difficulty", 1),
                    "prerequisites": topic.get("prerequisites", []),
                    "status": p.get("status") or "not_started",
                    "mastery_score": p.get("mastery_score") or 0,
                    "attempts": p.get("attempts") or 0,
                    "correct": p.get("correct") or 0,
                })
            units_out.append({
                "id": unit["id"],
                "title": unit["title"],
                "topics": topics_out,
            })
        tracks_out.append({
            "id": track["id"],
            "title": track["title"],
            "summary": track.get("summary", ""),
            "capstone_topic_id": track.get("capstone_topic_id"),
            "units": units_out,
        })
    return {"tracks": tracks_out}


@router.get("/summary")
async def progress_summary() -> dict:
    return await user_profile.get_summary()


@router.get("/topic/{topic_id}")
async def topic_detail(topic_id: str) -> dict:
    topic = curriculum.topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Unknown topic")
    history = await user_profile.get_topic_history(topic_id)
    sessions = await db.fetch_all(
        "SELECT id, started_at, ended_at, outcome, mode, domain, summary "
        "FROM sessions WHERE topic_id = ? ORDER BY id DESC LIMIT 20",
        (topic_id,),
    )
    return {
        "topic": topic,
        "history": history,
        "sessions": sessions,
    }


class DomainPayload(BaseModel):
    domain: str


@router.post("/preferred_domain")
async def set_preferred_domain(p: DomainPayload) -> dict:
    await user_profile.set_preferred_domain(p.domain)
    return {"ok": True}


@router.get("/capstone/{track_id}", response_model=CapstoneState)
async def get_capstone(track_id: str) -> CapstoneState:
    row = await db.fetch_one(
        "SELECT phase, checkpoints, scratchpad FROM capstone_progress WHERE track_id = ?",
        (track_id,),
    )
    if not row:
        return CapstoneState(track_id=track_id, phase="not_started", checkpoints=[], scratchpad="")
    try:
        checkpoints = json.loads(row["checkpoints"] or "[]")
    except json.JSONDecodeError:
        checkpoints = []
    return CapstoneState(
        track_id=track_id,
        phase=row["phase"] or "not_started",
        checkpoints=checkpoints,
        scratchpad=row["scratchpad"] or "",
    )


class CapstonePayload(BaseModel):
    track_id: str
    phase: str | None = None
    checkpoints: list[dict] | None = None
    scratchpad: str | None = None


@router.post("/capstone")
async def save_capstone(p: CapstonePayload) -> dict:
    existing = await db.fetch_one(
        "SELECT phase, checkpoints, scratchpad FROM capstone_progress WHERE track_id = ?",
        (p.track_id,),
    )
    phase = p.phase or (existing or {}).get("phase") or "not_started"
    checkpoints = p.checkpoints if p.checkpoints is not None else None
    scratchpad = p.scratchpad if p.scratchpad is not None else None

    if existing:
        await db.execute(
            "UPDATE capstone_progress SET phase = ?, "
            "checkpoints = COALESCE(?, checkpoints), "
            "scratchpad = COALESCE(?, scratchpad), updated_at = datetime('now') "
            "WHERE track_id = ?",
            (
                phase,
                json.dumps(checkpoints) if checkpoints is not None else None,
                scratchpad,
                p.track_id,
            ),
        )
    else:
        await db.execute(
            "INSERT INTO capstone_progress(track_id, phase, checkpoints, scratchpad) "
            "VALUES (?, ?, ?, ?)",
            (
                p.track_id,
                phase,
                json.dumps(checkpoints or []),
                scratchpad or "",
            ),
        )
    return {"ok": True}
