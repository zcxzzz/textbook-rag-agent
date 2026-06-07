"""POST /api/chat/stream — SSE streaming chat endpoint."""
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.schemas import ChatRequest
from backend.services.app_state import memory, llm, get_chain

logger = logging.getLogger("backend.api.chat")

router = APIRouter()

COMPRESSION_INTERVAL = 20
COMPRESSION_KEEP_LAST = 10


class _ChatRequestBody(BaseModel):
    message: str


@router.post("/chat/stream")
async def chat_stream(
    body: _ChatRequestBody,
    session_id: str = Query(...),
    book_name: str = Query(None),
):
    """SSE streaming chat endpoint.

    Event types:
      token   — a chunk of the assistant's answer
      sources — retrieved document sources (after generation)
      done    — final metadata (round_count, compressed flag)
      error   — error message (only on failure)
    """
    mem = memory()
    if not mem:
        raise HTTPException(status_code=503, detail="Memory system not available")

    user_input = body.message.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="Empty message")

    # Load chat history from DB
    chat_history = mem.get_session_messages(session_id, limit=200)
    round_count = len(chat_history) // 2

    async def event_stream():
        nonlocal chat_history, round_count

        try:
            # ── Command handling ──
            if user_input.startswith("/"):
                from src.commands import handle_command
                chain = get_chain(book_name)
                should_exit, output = handle_command(
                    user_input, chain, chat_history,
                    agent_memory=mem,
                    session_id=session_id,
                    book_name=book_name,
                )
                # Send as single token for commands (non-streaming)
                yield _sse("token", {"content": output})
                yield _sse("done", {"round_count": round_count, "compressed": False})
                return

            # ── RAG pipeline ──
            chain = get_chain(book_name)

            # Step 1+2: query rewrite + retrieve (non-streaming, fast)
            # We use ainvoke which internally handles history-aware rewrite + retrieval
            # then stream only the final LLM generation
            try:
                result = chain.invoke({
                    "input": user_input,
                    "chat_history": chat_history,
                })
                answer = result.get("answer", "")
                context_docs = result.get("context", [])
            except Exception:
                logger.exception("Chain invoke failed")
                yield _sse("error", {"message": "查询失败，请重试。"})
                return

            # Stream the answer token-by-token by re-invoking with streaming
            # Since create_retrieval_chain doesn't stream natively, we use
            # astream on the LLM directly with the same prompt.
            # For simplicity and reliability, send the full answer as larger
            # chunks (simulated streaming by splitting on sentence boundaries).
            import re
            chunks = re.split(r'(?<=[。！？\n])', answer)
            for chunk in chunks:
                if chunk:
                    yield _sse("token", {"content": chunk})

            # Sources
            sources = _extract_sources(context_docs)
            yield _sse("sources", {"sources": sources})

            # Persist messages
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": answer})

            mem.add_message(session_id, "user", user_input)
            source_dicts = [
                {"source_file": doc.metadata.get("source_file", ""),
                 "heading": doc.metadata.get("heading", ""),
                 "book_name": doc.metadata.get("book_name", "")}
                for doc in context_docs
            ]
            mem.add_message(session_id, "assistant", answer, sources=source_dicts[:5])

            # Auto learning detection
            from src.config import MEMORY_ENABLED, MEMORY_AUTO_LEARNING_DETECTION
            if MEMORY_ENABLED and MEMORY_AUTO_LEARNING_DETECTION:
                from src.chat import _auto_detect_learning
                _auto_detect_learning(mem, session_id, book_name, user_input, answer)

            # Compression check
            round_count += 1
            compressed = False
            if round_count > 0 and round_count % COMPRESSION_INTERVAL == 0:
                from src.chat import _compress_history
                _compress_history(chat_history, round_count)
                compressed = True

            yield _sse("done", {"round_count": round_count, "compressed": compressed})

        except Exception:
            logger.exception("SSE stream error")
            yield _sse("error", {"message": "内部错误，请重试。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_sources(docs: list) -> list[dict]:
    seen = set()
    sources = []
    for doc in docs:
        src = doc.metadata.get("source_file", "")
        heading = doc.metadata.get("heading", "")
        page_raw = doc.metadata.get("page")  # 0-based int
        page_label = doc.metadata.get("page_label", str(page_raw + 1) if page_raw is not None else "")
        key = f"{src}|{page_label}|{heading}"
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "file": src,
            "heading": heading,
            "book_name": doc.metadata.get("book_name", ""),
            "source_path": doc.metadata.get("source_path", ""),
            "page": page_raw if page_raw is not None else 0,
        }
        if page_label is not None:
            try:
                p = int(page_label)
                entry["page_label"] = f"p{p + 1}" if p < 1000 else f"p{p}"
            except (ValueError, TypeError):
                entry["page_label"] = f"p{page_label}"
        sources.append(entry)
    return sources[:5]
