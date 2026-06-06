"""GET /api/books — list indexed textbooks."""
from fastapi import APIRouter

from src.chat import list_available_books

router = APIRouter()


@router.get("/books")
async def get_books():
    books = list_available_books()
    return {"books": books}
