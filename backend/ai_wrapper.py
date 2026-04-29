"""Single-entry-point wrapper for every AI call MathCore makes.

Supports two protocols:

* **Anthropic messages API** (``/v1/messages``) when ``base_url`` points at
  ``api.anthropic.com`` or ``provider_hint == "anthropic"``.
* **OpenAI-compatible chat completions** (``/chat/completions``) for
  OpenRouter, Chutes, local llama.cpp servers, LM Studio, vLLM, etc.

Every call is async. Errors raise ``AIProviderError`` so the FastAPI routes
can translate them into a user-friendly retry prompt instead of crashing.
"""
from __future__ import annotations

import json
import re
from typing import Any
from dataclasses import dataclass

import httpx

from backend import crypto
from backend.database import db


class AIProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model_name: str
    custom_system_prompt: str
    provider_hint: str  # auto | anthropic | openai

    @property
    def resolved_provider(self) -> str:
        if self.provider_hint in ("anthropic", "openai"):
            return self.provider_hint
        host = self.base_url.lower()
        if "anthropic" in host:
            return "anthropic"
        return "openai"


async def load_config() -> ProviderConfig | None:
    row = await db.fetch_one(
        "SELECT api_key_ciphertext, base_url, model_name, custom_system_prompt, provider_hint "
        "FROM app_config WHERE id = 1"
    )
    if not row:
        return None
    api_key = crypto.decrypt(row["api_key_ciphertext"])
    if not api_key:
        return None
    return ProviderConfig(
        api_key=api_key,
        base_url=row["base_url"].rstrip("/"),
        model_name=row["model_name"],
        custom_system_prompt=row["custom_system_prompt"] or "",
        provider_hint=row["provider_hint"] or "auto",
    )


def _merge_system_prompt(cfg: ProviderConfig, role_prompt: str) -> str:
    """Combine the user's custom system prompt with the topic/role prompt."""
    custom = (cfg.custom_system_prompt or "").strip()
    if custom:
        return f"{custom}\n\n---\n\n{role_prompt}".strip()
    return role_prompt.strip()


async def chat(
    system_prompt: str,
    messages: list[dict[str, str]],
    *,
    response_format: str = "text",
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Send a single chat turn. Returns the assistant's text response.

    ``messages`` must be a list of ``{"role": "user"|"assistant", "content": str}``
    entries. The ``system_prompt`` is merged with the user's custom prompt
    before being sent. ``response_format`` of ``"json"`` nudges the provider
    to return machine-readable output when supported.
    """
    cfg = await load_config()
    if cfg is None:
        raise AIProviderError("AI provider is not configured yet.", status=428)

    full_system = _merge_system_prompt(cfg, system_prompt)
    provider = cfg.resolved_provider

    timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if provider == "anthropic":
                return await _anthropic_call(
                    client, cfg, full_system, messages,
                    temperature=temperature, max_tokens=max_tokens,
                    response_format=response_format,
                )
            return await _openai_call(
                client, cfg, full_system, messages,
                temperature=temperature, max_tokens=max_tokens,
                response_format=response_format,
            )
        except UnicodeEncodeError as e:
            # HTTP headers must be ASCII; this almost always means the saved
            # API key contains a smart-quote, accent, or other non-ASCII char.
            raise AIProviderError(
                "API key or base URL contains non-ASCII characters. Open "
                "Settings, clear the configuration, and paste the key again "
                "from a plain-text source.",
                status=400,
            ) from e
        except httpx.HTTPError as e:
            raise AIProviderError(f"Network error talking to AI provider: {e}") from e


def _anthropic_base(base_url: str) -> str:
    """Strip any trailing ``/v1`` or ``/v1/messages`` so we can safely append ``/v1/messages``."""
    u = base_url.rstrip("/")
    for suffix in ("/v1/messages", "/v1"):
        if u.lower().endswith(suffix):
            return u[: -len(suffix)]
    return u


async def _anthropic_call(
    client: httpx.AsyncClient,
    cfg: ProviderConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    response_format: str,
) -> str:
    url = f"{_anthropic_base(cfg.base_url)}/v1/messages"
    payload: dict[str, Any] = {
        "model": cfg.model_name,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {"role": m["role"], "content": m["content"]} for m in messages
        ],
    }
    headers = {
        "x-api-key": cfg.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    r = await client.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        raise AIProviderError(_extract_error(r), status=r.status_code)
    data = r.json()
    parts = data.get("content") or []
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return "".join(texts).strip()


async def _openai_call(
    client: httpx.AsyncClient,
    cfg: ProviderConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    response_format: str,
) -> str:
    base = cfg.base_url.rstrip("/")
    if base.lower().endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    url = f"{base}/chat/completions"
    full_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    full_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)
    payload: dict[str, Any] = {
        "model": cfg.model_name,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    r = await client.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        raise AIProviderError(_extract_error(r), status=r.status_code)
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise AIProviderError("Provider returned no choices.")
    msg = choices[0].get("message", {})
    return (msg.get("content") or "").strip()


def _extract_error(r: httpx.Response) -> str:
    try:
        data = r.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            if err:
                return str(err)
            return json.dumps(data)[:500]
    except Exception:
        pass
    return f"HTTP {r.status_code}: {r.text[:500]}"


def _normalize_backslashes_in_json_strings(s: str) -> str:
    """Heuristically fix backslashes inside JSON string literals.

    Two common AI failure modes for math-heavy content:

    * **Invalid JSON**: AI emits ``"\\sqrt9"`` (literal backslash-s). JSON
      rejects it because ``\\s`` isn't a valid escape.
    * **Valid JSON but wrong content**: AI emits ``"\\frac"`` (literal
      backslash-f), which JSON parses as form-feed + ``rac``. KaTeX then
      shows "rac" with a phantom whitespace.

    Both are fixed by doubling backslashes that are clearly LaTeX commands
    (followed by a letter), while leaving genuine JSON escapes
    (``\\"``, ``\\\\``, ``\\/``, ``\\n``, ``\\t``, etc. -- when they're
    actually one-character escapes) intact. The disambiguation rule for
    ``\\b \\f \\n \\r \\t \\u``: if the next character is also alphabetic,
    treat it as a LaTeX command (``\\frac``, ``\\beta``, ``\\nu``,
    ``\\text``...). Otherwise treat it as a JSON escape.

    Runs only on the body of JSON string literals -- structure outside
    strings is preserved untouched so the parser can still see the object.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    in_string = False
    while i < n:
        c = s[i]
        if c == '"':
            # Toggle string state, but only if not escaped.
            backslashes = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                in_string = not in_string
            out.append(c)
            i += 1
            continue
        if in_string and c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "\\":
                # Already-escaped backslash pair -- keep as-is.
                out.append("\\\\")
                i += 2
                continue
            if nxt in '"/':
                # Genuine JSON escape we don't want to touch.
                out.append(c)
                out.append(nxt)
                i += 2
                continue
            if nxt in "bfnrtu":
                # Ambiguous: JSON escape OR start of a LaTeX command.
                # If the char two ahead is alphabetic, treat the sequence
                # as LaTeX (e.g. \frac, \beta, \nu, \text, \udelim...).
                ahead = s[i + 2] if i + 2 < n else ""
                if ahead.isalpha():
                    out.append("\\\\")
                    out.append(nxt)
                    i += 2
                else:
                    out.append(c)
                    out.append(nxt)
                    i += 2
                continue
            if nxt.isalpha():
                # Definitely a LaTeX command (\sqrt, \pi, \alpha, ...).
                out.append("\\\\")
                out.append(nxt)
                i += 2
                continue
            # Anything else (digit, punctuation): leave alone.
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


async def parse_json_response(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an AI text reply.

    Handles common AI mistakes:

    1. Markdown fences (```json ... ```), stripped before parsing.
    2. Strict JSON, parsed directly.
    3. Unescaped LaTeX backslashes (``\\sqrt``, ``\\frac``, ...) inside
       JSON string literals -- normalized via heuristic and retried.
    4. Raw newlines/tabs leaked into string literals.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return {}
    candidate = cleaned[start : end + 1]

    # Try a sequence of progressively more aggressive repairs and pick the
    # first parse whose ``assistant_message`` has no stray control chars.
    repairs: list[str] = [candidate]
    repairs.append(_normalize_backslashes_in_json_strings(candidate))
    repairs.append(
        re.sub(
            r"(?<!\\)\t",
            r"\\t",
            re.sub(
                r"(?<!\\)\n",
                r"\\n",
                _normalize_backslashes_in_json_strings(candidate),
            ),
        )
    )

    fallback: dict[str, Any] | None = None
    for rep in repairs:
        try:
            data = json.loads(rep)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "assistant_message" not in data:
            continue
        msg = data.get("assistant_message", "")
        if isinstance(msg, str) and not any(
            ord(ch) < 0x20 and ch not in "\n\r\t" for ch in msg
        ):
            return data
        if fallback is None:
            fallback = data

    return fallback or {}
