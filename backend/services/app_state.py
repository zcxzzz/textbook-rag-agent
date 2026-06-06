"""
Module-level singletons — replace Streamlit's @st.cache_resource.
Heavy models load once at lifespan startup, shared across all requests.
"""
import logging
import sys
import threading
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import (
    LLM_MODEL, MEMORY_ENABLED, MEMORY_DB_PATH, RERANK_ENABLED,
    get_embeddings as _get_embeddings,
    get_llm as _get_llm,
)

logger = logging.getLogger("backend.app_state")

_lock = threading.Lock()

# ---- The 5 singletons ----
_embeddings = None       # HuggingFaceEmbeddings (~2.3 GB)
_llm = None              # ChatOpenAI client
_reranker = None         # CrossEncoderReranker (~1.3 GB)
_memory = None           # AgentMemory (SQLite)
_chain_cache: dict = {}  # book_name → chain


def warmup():
    """Load all heavy resources. Called once at FastAPI lifespan startup."""
    global _embeddings, _llm, _reranker, _memory

    logger.info("Loading embedding model …")
    _embeddings = _get_embeddings()

    logger.info("Creating LLM client …")
    _llm = _get_llm()

    if RERANK_ENABLED:
        try:
            from src.reranker import CrossEncoderReranker
            logger.info("Loading reranker model …")
            _reranker = CrossEncoderReranker()
        except Exception:
            logger.warning("Reranker failed to load, will skip reranking")

    if MEMORY_ENABLED:
        try:
            from src.memory import AgentMemory
            logger.info("Initialising AgentMemory (SQLite) …")
            _memory = AgentMemory(MEMORY_DB_PATH, llm_factory=_get_llm)
        except Exception:
            logger.warning("AgentMemory failed to init — long-term memory disabled")


def shutdown():
    """Clean up. Called at FastAPI lifespan shutdown."""
    global _memory
    if _memory:
        try:
            _memory.close()
            logger.info("AgentMemory closed")
        except Exception:
            pass


# ---- Accessors ----

def embeddings():
    return _embeddings


def llm():
    return _llm


def reranker():
    return _reranker


def memory():
    return _memory


def get_chain(book_name: str | None):
    """Return a cached RAG chain for the given book. Builds on first access."""
    if book_name not in _chain_cache:
        with _lock:
            if book_name not in _chain_cache:
                _chain_cache[book_name] = _build_chain(book_name)
    return _chain_cache[book_name]


# ---- Internal chain builder ----

def _build_chain(book_name: str | None):
    from langchain_classic.chains import create_history_aware_retriever
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnableLambda
    from src.config import (
        QUERY_EXPANSION_ENABLED, METADATA_FILTER_ENABLED, HYBRID_SEARCH_ENABLED,
    )
    from src.chat import list_available_books
    from src.prompt_templates import build_system_prompt

    # Build retriever
    try:
        from src.retriever import EnhancedRetriever
        r = EnhancedRetriever(
            book_name=book_name,
            embeddings=_embeddings,
            reranker=_reranker,
            enable_query_expansion=QUERY_EXPANSION_ENABLED,
            enable_metadata_filter=METADATA_FILTER_ENABLED,
            enable_hybrid=HYBRID_SEARCH_ENABLED,
        )
    except Exception:
        from langchain_chroma import Chroma
        from src.config import get_chroma_dir
        logger.warning("EnhancedRetriever failed, falling back to base MMR")
        books = list_available_books()
        if not books:
            raise RuntimeError("No indexed textbooks")
        chroma_dir = get_chroma_dir(book_name or books[0])
        vs = Chroma(persist_directory=chroma_dir, embedding_function=_embeddings)
        r = vs.as_retriever(search_type="mmr", search_kwargs={"k": 8, "fetch_k": 20})

    retriever = RunnableLambda(lambda q, **kw: r.invoke(q))

    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system", "根据对话历史，将用户的问题重新表述为一个独立的、完整的检索查询。如果用户的问题已经足够独立，直接返回原问题。只返回重新表述的问题，不要加任何额外内容。"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    history_aware_retriever = create_history_aware_retriever(
        _llm, retriever, contextualize_prompt,
    )

    system_prompt = build_system_prompt(_memory, book_name)
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    qa_chain = create_stuff_documents_chain(_llm, qa_prompt)
    return create_retrieval_chain(history_aware_retriever, qa_chain)
