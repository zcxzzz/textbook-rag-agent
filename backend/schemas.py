"""Pydantic models for request / response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message or /command")


class SourceChunk(BaseModel):
    file: str
    page: str | None = None
    heading: str | None = None


class TokenEvent(BaseModel):
    content: str


class SourcesEvent(BaseModel):
    sources: list[SourceChunk]


class DoneEvent(BaseModel):
    round_count: int
    compressed: bool = False


class ErrorEvent(BaseModel):
    message: str


# ── Sessions ──────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    book_name: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    book_name: str | None
    created_at: str
    closed_at: str | None
    total_messages: int
    summary: str | None


class Message(BaseModel):
    role: str
    content: str

class Result(BaseModel):
    status: str
    message: str
# ── Progress ──────────────────────────────────────────────────

class LearningRecord(BaseModel):
    book_name: str
    chapter: str
    topic: str
    mastered: int
    last_reviewed: str | None


class WeakPoint(BaseModel):
    book_name: str
    topic: str
    error_count: int
    last_error_at: str | None
    resolved: int


class StudentProfile(BaseModel):
    book_name: str
    overall_level: str
    notes: str | None
    created_at: str | None
    updated_at: str | None


class UpdateProfileRequest(BaseModel):
    overall_level: str | None = None
    notes: str | None = None


class StatsResponse(BaseModel):
    total_sessions: int
    total_topics_learned: int
    active_weak_points: int
