"""
FastAPI entry point for Textbook-RAG-Agent.
Usage: uvicorn backend.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.books import router as books_router
from backend.api.sessions import router as sessions_router
from backend.api.progress import router as progress_router
from backend.api.chat import router as chat_router
from backend.api.pages import router as pages_router

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load heavy models on startup, clean up on shutdown."""
    from backend.services.app_state import warmup, shutdown
    logger.info("Starting up — loading models …")
    warmup()
    logger.info("Ready.")
    yield
    logger.info("Shutting down …")
    shutdown()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Textbook-RAG-Agent API",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(progress_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(pages_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
