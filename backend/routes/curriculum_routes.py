"""/api/curriculum -- static curriculum structure (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services.curriculum_service import curriculum


router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])


@router.get("")
async def get_all() -> dict:
    return curriculum.all()


@router.get("/domains")
async def list_domains() -> dict:
    return {"domains": curriculum.domains()}


@router.get("/topic/{topic_id}")
async def get_topic(topic_id: str) -> dict:
    t = curriculum.topic(topic_id)
    if not t:
        raise HTTPException(status_code=404, detail="Unknown topic")
    return t
