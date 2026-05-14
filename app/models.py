from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel


# ── Pydantic request/response models ────────────────────────────────────────

class TanCheckRequest(BaseModel):
    tan: str


class TanCheckResponse(BaseModel):
    valid: bool
    survey_id: int | None = None
    class_name: str | None = None
    questionnaire: dict[str, Any] | None = None
    error: str | None = None


class SubmitRequest(BaseModel):
    tan: str
    answers: dict[str, Any]


class SubmitResponse(BaseModel):
    ok: bool
    error: str | None = None


class SurveyCreateRequest(BaseModel):
    title: str
    survey_type: str
    questionnaire_id: str
    starts_at: str
    ends_at: str


class ClassAddRequest(BaseModel):
    name: str


class TanGenerateRequest(BaseModel):
    class_name: str
    count: int


# ── Internal dataclasses ─────────────────────────────────────────────────────

@dataclass
class User:
    id: int
    username: str
    role: str
    must_change_password: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "schulleitung"


@dataclass
class Survey:
    id: int
    title: str
    survey_type: str
    questionnaire_id: str
    starts_at: str
    ends_at: str
    status: str
    created_at: str


@dataclass
class SurveyClass:
    id: int
    survey_id: int
    name: str


@dataclass
class Tan:
    id: int
    code: str
    class_id: int
    survey_id: int
    used_at: str | None
    created_at: str


@dataclass
class Response:
    id: int
    survey_id: int
    class_name: str
    submitted_at: str
    payload_json: str


@dataclass
class ClassStats:
    name: str
    total_tans: int
    used_tans: int
    responses: int
