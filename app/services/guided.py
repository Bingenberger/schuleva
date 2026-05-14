"""In-memory session management for guided survey mode."""
from __future__ import annotations
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

SAFE_CHARS = "ABCDEFGHJKLMNPQRTVWXYZ2346789"
SESSION_TTL = 4 * 3600  # sessions expire after 4 hours


def _gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(SAFE_CHARS) for _ in range(n))


@dataclass
class StudentConn:
    ws: Any                                       # WebSocket
    answers: dict[str, str] = field(default_factory=dict)
    answered_current: bool = False


@dataclass
class GuidedSession:
    session_id: str
    survey_id: int
    class_name: str
    questionnaire: dict
    questions: list[dict]   # flattened questions (each has _section_title)
    scale: dict

    teacher_ws: Optional[Any] = None
    students: dict[str, StudentConn] = field(default_factory=dict)

    phase: str = "lobby"    # "lobby" | "survey" | "ended"
    q_idx: int = 0
    unlocked: bool = False
    created_at: float = field(default_factory=time.time)


_sessions: dict[str, GuidedSession] = {}


def create_session(survey_id: int, class_name: str, questionnaire: dict) -> GuidedSession:
    questions: list[dict] = []
    for sec in questionnaire.get("sections", []):
        for q in sec.get("questions", []):
            questions.append({**q, "_section_title": sec.get("title", "")})

    session_id = _gen_code(6)
    while session_id in _sessions:
        session_id = _gen_code(6)

    session = GuidedSession(
        session_id=session_id,
        survey_id=survey_id,
        class_name=class_name,
        questionnaire=questionnaire,
        questions=questions,
        scale=questionnaire.get("scale", {}),
    )
    _sessions[session_id] = session
    _purge_old()
    return session


def get_session(session_id: str) -> Optional[GuidedSession]:
    return _sessions.get(session_id)


def _purge_old() -> None:
    cutoff = time.time() - SESSION_TTL
    stale = [k for k, s in _sessions.items() if s.created_at < cutoff]
    for k in stale:
        del _sessions[k]
