"""Session CRUD endpoints."""
from fastapi import APIRouter, HTTPException

from backend.schemas import CreateSessionRequest, SessionInfo, Message
from backend.services.app_state import memory

router = APIRouter()


@router.post("/sessions", response_model=SessionInfo)
async def create_session(req: CreateSessionRequest):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    sid = mem.create_session(req.book_name)
    if req.book_name:
        mem.conn.execute(
            "UPDATE sessions SET book_name = ? WHERE session_id = ?",
            (req.book_name, sid),
        )
        mem.conn.commit()
    row = dict(mem.conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (sid,)
    ).fetchone())
    return _row_to_session_info(row)


@router.post("/sessions/{session_id}/resume", response_model=SessionInfo)
async def resume_session(session_id: str):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    info = mem.reopen_session(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    row = dict(mem.conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone())
    return _row_to_session_info(row)


@router.get("/sessions/{session_id}/messages", response_model=list[Message])
async def get_messages(session_id: str, limit: int = 100):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    msgs = mem.get_session_messages(session_id, limit=limit)
    return [Message(role=m["role"], content=m["content"]) for m in msgs]


@router.get("/sessions/history", response_model=list[SessionInfo])
async def session_history(limit: int = 20):
    mem = memory()
    if not mem:
        return []
    sessions = mem.get_recent_sessions(limit=limit)
    return [_row_to_session_info(s) for s in sessions]


# ── helpers ──

def _row_to_session_info(row: dict) -> SessionInfo:
    return SessionInfo(
        session_id=row["session_id"],
        book_name=row.get("book_name"),
        created_at=str(row.get("created_at", "")),
        closed_at=str(row.get("closed_at")) if row.get("closed_at") else None,
        total_messages=row.get("total_messages") or 0,
        summary=row.get("summary"),
    )
