"""/api/session -- start, turn, end, and history."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import ai_wrapper
from backend.database import db
from backend.models import (
    StartSessionPayload,
    ChatMessagePayload,
    ChatTurnResponse,
    EndSessionPayload,
)
from backend.services import session_service
from backend.services.curriculum_service import curriculum


router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("/start", response_model=ChatTurnResponse)
async def start(p: StartSessionPayload) -> ChatTurnResponse:
    try:
        result = await session_service.start_session(
            topic_id=p.topic_id, mode=p.mode, domain_hint=p.domain_hint
        )
    except ai_wrapper.AIProviderError as e:
        raise HTTPException(status_code=e.status or 502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ChatTurnResponse(**result)


@router.post("/turn", response_model=ChatTurnResponse)
async def turn(p: ChatMessagePayload) -> ChatTurnResponse:
    try:
        result = await session_service.handle_turn(
            session_id=p.session_id, user_content=p.content, action=p.action
        )
    except ai_wrapper.AIProviderError as e:
        raise HTTPException(status_code=e.status or 502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ChatTurnResponse(**result)


@router.post("/end")
async def end(p: EndSessionPayload) -> dict:
    await session_service.end_session(p.session_id, outcome=p.outcome)
    return {"ok": True}


@router.get("/history/{session_id}")
async def history(session_id: int) -> dict:
    messages = await session_service.load_history(session_id)
    session = await db.fetch_one(
        "SELECT id, topic_id, track_id, domain, mode, outcome FROM sessions WHERE id = ?",
        (session_id,),
    )
    topic = None
    if session:
        topic = curriculum.topic(session["topic_id"])
    usage = await session_service.session_context_usage(session_id)
    return {
        "messages": messages,
        "session": session,
        "topic": topic,
        "tokens_estimate": usage["tokens_estimate"],
    }


@router.get("/active/{topic_id}")
async def active(topic_id: str) -> dict:
    """Return the most recent resumable session for ``topic_id``.

    A session is "resumable" if it has not been explicitly finalized
    (``ended_at IS NULL``) -- this covers both checkpointed sessions
    (Save & exit) and sessions abandoned by closing the browser/app.
    Returns ``{"session_id": null}`` if there is nothing to resume.
    """
    row = await db.fetch_one(
        "SELECT id FROM sessions WHERE topic_id = ? AND ended_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (topic_id,),
    )
    return {"session_id": row["id"] if row else None}
