"""/api/ai -- generic free-form AI call for auxiliary UI features."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import ai_wrapper


router = APIRouter(prefix="/api/ai", tags=["ai"])


class QuickAsk(BaseModel):
    system: str | None = None
    prompt: str


@router.post("/ask")
async def ask(p: QuickAsk) -> dict:
    try:
        text = await ai_wrapper.chat(
            system_prompt=p.system or "You are a concise mathematics helper.",
            messages=[{"role": "user", "content": p.prompt}],
            max_tokens=600,
            temperature=0.3,
        )
    except ai_wrapper.AIProviderError as e:
        raise HTTPException(status_code=e.status or 502, detail=str(e))
    return {"reply": text}
