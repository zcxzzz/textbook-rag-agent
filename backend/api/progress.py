"""Learning progress / weak points / profile / stats endpoints."""
from fastapi import APIRouter, HTTPException, Query

from backend.schemas import (
    LearningRecord, WeakPoint, StudentProfile,
    UpdateProfileRequest, StatsResponse,
)
from backend.services.app_state import memory

router = APIRouter()


@router.get("/progress", response_model=list[LearningRecord])
async def get_progress(book_name: str = Query(None)):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    records = mem.get_all_progress(book_name)
    return [
        LearningRecord(
            book_name=r.get("book_name", ""),
            chapter=r.get("chapter", ""),
            topic=r.get("topic", ""),
            mastered=r.get("mastered", 0),
            last_reviewed=str(r.get("last_reviewed")) if r.get("last_reviewed") else None,
        )
        for r in records
    ]


@router.get("/weakpoints", response_model=list[WeakPoint])
async def get_weakpoints(book_name: str = Query(None), active_only: bool = True):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    points = mem.get_weak_points(book_name, active_only=active_only)
    return [
        WeakPoint(
            book_name=p.get("book_name", ""),
            topic=p.get("topic", ""),
            error_count=p.get("error_count", 0),
            last_error_at=str(p.get("last_error_at")) if p.get("last_error_at") else None,
            resolved=p.get("resolved", 0),
        )
        for p in points
    ]


@router.get("/profile", response_model=StudentProfile)
async def get_profile(book_name: str = Query(...)):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    profile = mem.get_profile(book_name)
    if not profile:
        mem.upsert_profile(book_name, overall_level="beginner")
        profile = mem.get_profile(book_name)
    return StudentProfile(
        book_name=profile.get("book_name", book_name),
        overall_level=profile.get("overall_level", "beginner"),
        notes=profile.get("notes"),
        created_at=str(profile.get("created_at")) if profile.get("created_at") else None,
        updated_at=str(profile.get("updated_at")) if profile.get("updated_at") else None,
    )


@router.put("/profile", response_model=StudentProfile)
async def update_profile(book_name: str = Query(...), req: UpdateProfileRequest = None):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    kwargs = {}
    if req and req.overall_level:
        kwargs["overall_level"] = req.overall_level
    if req and req.notes is not None:
        kwargs["notes"] = req.notes
    if kwargs:
        mem.upsert_profile(book_name, **kwargs)
    return await get_profile(book_name=book_name)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(book_name: str = Query(None)):
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")
    s = mem.get_stats(book_name)
    return StatsResponse(
        total_sessions=s["total_sessions"],
        total_topics_learned=s["total_topics_learned"],
        active_weak_points=s["active_weak_points"],
    )
