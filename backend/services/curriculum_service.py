"""Curriculum loader.

Loads ``data/curriculum.json`` once and exposes lookup helpers. The file is
read-only scaffolding -- the AI generates actual content dynamically -- so
reloading is unnecessary during normal operation.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from typing import Any


def _curriculum_path() -> Path:
    env = os.environ.get("MATHCORE_DATA_DIR")
    if env:
        candidate = Path(env) / "curriculum.json"
        if candidate.exists():
            return candidate
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        bundled = base / "data" / "curriculum.json"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parents[2] / "data" / "curriculum.json"


class CurriculumService:
    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None
        self._topic_index: dict[str, dict[str, Any]] = {}
        self._unit_index: dict[str, dict[str, Any]] = {}
        self._track_index: dict[str, dict[str, Any]] = {}

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        path = _curriculum_path()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._data = data
        for track in data.get("tracks", []):
            self._track_index[track["id"]] = track
            for unit in track.get("units", []):
                self._unit_index[unit["id"]] = {**unit, "track_id": track["id"]}
                for topic in unit.get("topics", []):
                    self._topic_index[topic["id"]] = {
                        **topic,
                        "track_id": track["id"],
                        "unit_id": unit["id"],
                        "unit_title": unit["title"],
                        "track_title": track["title"],
                    }
        return data

    def all(self) -> dict[str, Any]:
        return self._load()

    def track(self, track_id: str) -> dict[str, Any] | None:
        self._load()
        return self._track_index.get(track_id)

    def unit(self, unit_id: str) -> dict[str, Any] | None:
        self._load()
        return self._unit_index.get(unit_id)

    def topic(self, topic_id: str) -> dict[str, Any] | None:
        self._load()
        return self._topic_index.get(topic_id)

    def domains(self) -> list[str]:
        return self._load().get("domains", [])

    def is_capstone(self, topic_id: str) -> bool:
        self._load()
        for track in self._data.get("tracks", []):  # type: ignore[union-attr]
            if track.get("capstone_topic_id") == topic_id:
                return True
        return False

    def prerequisite_chain(self, topic_id: str) -> list[str]:
        self._load()
        seen: list[str] = []
        stack = [topic_id]
        while stack:
            cur = stack.pop()
            topic = self._topic_index.get(cur)
            if not topic:
                continue
            for prereq in topic.get("prerequisites", []):
                if prereq not in seen:
                    seen.append(prereq)
                    stack.append(prereq)
        return seen


curriculum = CurriculumService()
