"""
Streamlit Web UI — Textbook RAG Tutor.
Usage: streamlit run app.py
"""
import logging
import sys
from pathlib import Path

import streamlit as st

# 确保 src/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from src.config import (
    INDEXES_DIR, LLM_MODEL, MEMORY_ENABLED, MEMORY_DB_PATH,
    RERANK_ENABLED, QUERY_EXPANSION_ENABLED, METADATA_FILTER_ENABLED,
    HYBRID_SEARCH_ENABLED, MEMORY_AUTO_LEARNING_DETECTION,
    get_embeddings, get_llm, get_chroma_dir,
)
from src.constants import SEP
from src.chat import (
    list_available_books, _compress_history, _auto_detect_learning,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("streamlit_app")

COMPRESSION_INTERVAL = 20
COMPRESSION_KEEP_LAST = 10

# ═══════════════════════════════════════════════════════════════
# Page Config
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Textbook RAG Tutor",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════
# Session State Init
# ═══════════════════════════════════════════════════════════════
DEFAULTS = {
    "initialized": False,
    "book_name": None,
    "session_id": None,
    "chat_history": [],
    "messages_to_render": [],  # 用于 UI 渲染的消息列表（含 sources）
    "round_count": 0,
    "chain_book_name": None,   # 当前 chain 对应的教材，用于检测切换
    "show_exit": False,
    "pending_command": None,   # 快捷命令按钮设置的待执行命令
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════
# Cached Heavy Resources (load once, share across all sessions)
# ═══════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def load_embeddings():
    """加载嵌入模型 (~2.3GB, 仅首次)。"""
    return get_embeddings()


@st.cache_resource(show_spinner=False)
def load_llm():
    """创建 LLM 客户端。"""
    return get_llm()


@st.cache_resource(show_spinner=False)
def load_reranker():
    """加载重排序模型 (~1.3GB, 仅首次)。"""
    from src.reranker import CrossEncoderReranker
    return CrossEncoderReranker()


@st.cache_resource(show_spinner=False)
def load_memory():
    """初始化 AgentMemory (SQLite)。"""
    from src.memory import AgentMemory
    return AgentMemory(MEMORY_DB_PATH, llm_factory=get_llm)


@st.cache_resource(show_spinner=False)
def load_chain(_book_name: str | None):
    """构建 RAG 链。_book_name 变化时自动重建。"""
    _embeddings = load_embeddings()
    _llm = load_llm()
    _memory = load_memory()

    from src.config import RERANK_ENABLED, QUERY_EXPANSION_ENABLED
    from src.config import METADATA_FILTER_ENABLED, HYBRID_SEARCH_ENABLED
    from langchain_core.runnables import RunnableLambda

    # 构建检索器
    try:
        from src.retriever import EnhancedRetriever
        reranker = None
        if RERANK_ENABLED:
            try:
                reranker = load_reranker()
            except Exception:
                logger.warning("重排序器加载失败")
        retriever_raw = EnhancedRetriever(
            book_name=_book_name,
            embeddings=_embeddings,
            reranker=reranker,
            enable_query_expansion=QUERY_EXPANSION_ENABLED,
            enable_metadata_filter=METADATA_FILTER_ENABLED,
            enable_hybrid=HYBRID_SEARCH_ENABLED,
        )
    except Exception:
        from langchain_chroma import Chroma
        logger.warning("EnhancedRetriever 加载失败，使用基础检索器")
        books = list_available_books()
        if not books:
            raise RuntimeError("没有已索引的教材")
        chroma_dir = get_chroma_dir(_book_name or books[0])
        vs = Chroma(persist_directory=chroma_dir, embedding_function=_embeddings)
        retriever_raw = vs.as_retriever(
            search_type="mmr", search_kwargs={"k": 8, "fetch_k": 20},
        )

    retriever = RunnableLambda(lambda q, **kw: retriever_raw.invoke(q))

    # 链构建
    from langchain_classic.chains import create_history_aware_retriever
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system", """根据对话历史，将用户的问题重新表述为一个独立的、完整的检索查询。
如果用户的问题已经足够独立，直接返回原问题。只返回重新表述的问题，不要加任何额外内容。"""),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    history_aware_retriever = create_history_aware_retriever(
        _llm, retriever, contextualize_prompt,
    )

    from src.prompt_templates import build_system_prompt
    system_prompt = build_system_prompt(_memory, _book_name)

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    qa_chain = create_stuff_documents_chain(_llm, qa_prompt)
    return create_retrieval_chain(history_aware_retriever, qa_chain)


# ═══════════════════════════════════════════════════════════════
# Session Lifecycle
# ═══════════════════════════════════════════════════════════════

def _new_session(book_name: str | None):
    """创建新会话。"""
    if not MEMORY_ENABLED:
        return
    memory = load_memory()
    sid = memory.create_session(book_name)
    memory.conn.execute(
        "UPDATE sessions SET book_name = ? WHERE session_id = ?",
        (book_name, sid),
    )
    memory.conn.commit()
    st.session_state.session_id = sid
    st.session_state.chat_history = []
    st.session_state.messages_to_render = []
    st.session_state.round_count = 0
    st.query_params["session"] = sid


def _resume_session(target_sid: str):
    """恢复已有会话。"""
    memory = load_memory()
    info = memory.reopen_session(target_sid)
    if not info:
        st.error(f"会话 {target_sid[:12]}... 不存在")
        return False

    history = memory.get_session_messages(target_sid, limit=100)
    st.session_state.session_id = target_sid
    st.session_state.chat_history = history
    st.session_state.messages_to_render = [{"role": m["role"], "content": m["content"]}
                                            for m in history]
    st.session_state.round_count = len(history) // 2
    st.session_state.book_name = info.get("book_name")
    st.query_params["session"] = target_sid
    return True


def _close_current_session():
    """关闭当前会话并显示退出信息。"""
    sid = st.session_state.session_id
    if not sid or not MEMORY_ENABLED:
        return
    memory = load_memory()

    # 保存学习快照
    try:
        from src.commands import _save_learning_snapshot
        _save_learning_snapshot(memory, sid, st.session_state.book_name,
                                st.session_state.chat_history)
    except Exception:
        pass

    memory.close_session(sid)
    st.session_state.show_exit = True


# ═══════════════════════════════════════════════════════════════
# Message Processing
# ═══════════════════════════════════════════════════════════════

def _process_message(user_input: str):
    """处理用户输入：命令分发或 RAG 查询。"""
    if not user_input.strip():
        return

    book_name = st.session_state.book_name
    sid = st.session_state.session_id
    memory = load_memory() if MEMORY_ENABLED else None
    chat_history = st.session_state.chat_history

    # 添加用户消息到渲染列表
    st.session_state.messages_to_render.append({
        "role": "user", "content": user_input,
    })

    # 命令处理
    if user_input.startswith("/"):
        _handle_command(user_input, memory, sid, book_name)
        return

    # RAG 查询
    chain = load_chain(book_name)
    with st.spinner("正在检索教材并生成回答..."):
        try:
            result = chain.invoke({
                "input": user_input,
                "chat_history": chat_history,
            })
            answer = result["answer"]
            sources = _extract_sources(result.get("context", []))
        except Exception as e:
            logger.exception("RAG 查询失败")
            answer = f"抱歉，查询时发生错误：{e}"
            sources = []

    # 添加助手消息
    st.session_state.messages_to_render.append({
        "role": "assistant", "content": answer, "sources": sources,
    })

    # 更新历史
    chat_history.append({"role": "user", "content": user_input})
    chat_history.append({"role": "assistant", "content": answer})

    # 持久化
    if memory and sid:
        source_dicts = [
            {"source_file": doc.metadata.get("source_file", ""),
             "heading": doc.metadata.get("heading", ""),
             "book_name": doc.metadata.get("book_name", "")}
            for doc in result.get("context", [])
        ]
        memory.add_message(sid, "user", user_input)
        memory.add_message(sid, "assistant", answer, sources=source_dicts[:5])

    # 自动学习检测
    if memory and MEMORY_ENABLED and sid and book_name:
        _auto_detect_learning(memory, sid, book_name, user_input, answer)

    # 压缩检查
    st.session_state.round_count += 1
    if st.session_state.round_count > 0 and st.session_state.round_count % COMPRESSION_INTERVAL == 0:
        _compress_history(st.session_state.chat_history, st.session_state.round_count)
        st.toast("对话上下文已压缩", icon="🗜️")


def _handle_command(cmd: str, memory, sid: str, book_name: str | None):
    """处理斜杠命令。"""
    from src.commands import handle_command
    chat_history = st.session_state.chat_history
    chain = load_chain(book_name)

    try:
        should_exit, output = handle_command(
            cmd, chain, chat_history,
            agent_memory=memory,
            session_id=sid,
            book_name=book_name,
        )
    except Exception as e:
        output = f"命令执行出错: {e}"
        should_exit = False

    st.session_state.messages_to_render.append({
        "role": "assistant", "content": output,
    })

    if should_exit:
        _close_current_session()


def _extract_sources(docs: list) -> list[dict]:
    """从检索文档提取来源信息。"""
    seen = set()
    sources = []
    for doc in docs:
        src = doc.metadata.get("source_file", "")
        heading = doc.metadata.get("heading", "")
        page = doc.metadata.get("page_label") or doc.metadata.get("page")
        key = f"{src}|{page}|{heading}"
        if key in seen:
            continue
        seen.add(key)
        entry = {"file": src, "heading": heading}
        if page is not None:
            try:
                p = int(page)
                entry["page"] = f"p{p + 1}" if p < 1000 else f"p{p}"
            except (ValueError, TypeError):
                entry["page"] = f"p{page}"
        sources.append(entry)
    return sources[:5]


# ═══════════════════════════════════════════════════════════════
# UI Rendering
# ═══════════════════════════════════════════════════════════════

def render():
    """主渲染入口。"""
    from src.streamlit_ui import (
        render_sidebar, render_chat_area, render_input_area,
        render_exit_screen, render_loading_screen,
    )

    # 加载阶段
    if not st.session_state.initialized:
        render_loading_screen()
        return

    # 退出画面
    if st.session_state.show_exit:
        render_exit_screen()
        return

    # 侧边栏（通过 _sidebar_action 标志传递操作）
    render_sidebar()

    # 处理侧边栏操作
    action = st.session_state.pop("_sidebar_action", None)
    action_data = st.session_state.pop("_sidebar_action_data", None)
    if action == "book_change":
        _close_current_session()
        st.session_state.book_name = action_data
        st.session_state.chain_book_name = None
        _new_session(action_data)
        st.session_state.show_exit = False
        # 同步 _prev_book_label 避免下次渲染重复触发
        st.session_state._prev_book_label = "全部教材" if action_data is None else action_data
        st.rerun()
    elif action == "new_session":
        _close_current_session()
        _new_session(st.session_state.book_name)
        st.session_state.show_exit = False
        st.rerun()
    elif action == "resume":
        ok = _resume_session(action_data)
        if ok:
            st.session_state.chain_book_name = None
            st.session_state.show_exit = False
            # 同步 _prev_book_label
            bk = st.session_state.book_name
            st.session_state._prev_book_label = "全部教材" if bk is None else bk
        st.rerun()

    # 处理快捷命令
    if st.session_state.pending_command:
        cmd = st.session_state.pending_command
        st.session_state.pending_command = None
        _process_message(cmd)

    # 聊天区域
    render_chat_area(st.session_state.messages_to_render)

    # 输入区域
    user_input = render_input_area()
    if user_input:
        _process_message(user_input)
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# Initialization
# ═══════════════════════════════════════════════════════════════

def _init_app():
    """首次加载：初始化资源 + 会话。"""
    if st.session_state.initialized:
        return

    # 检查教材
    books = list_available_books()
    if not books:
        st.error("未找到已索引的教材。请先运行: python -m src.ingest")
        st.stop()

    # 加载重量级资源
    with st.spinner("正在加载嵌入模型 (BGE-M3) ..."):
        load_embeddings()
    with st.spinner("正在加载 LLM 客户端 ..."):
        load_llm()
    if RERANK_ENABLED:
        with st.spinner("正在加载重排序模型 (BGE Reranker) ..."):
            try:
                load_reranker()
            except Exception:
                logger.warning("重排序器加载失败，将跳过重排序")

    # 会话恢复
    params = st.query_params
    resume_sid = params.get("session", None)

    if resume_sid and MEMORY_ENABLED:
        if _resume_session(resume_sid):
            st.session_state.initialized = True
            st.session_state.chain_book_name = None
            return

    # 默认：选择第一本教材，创建新会话
    default_book = books[0] if len(books) == 1 else None
    st.session_state.book_name = default_book
    _new_session(default_book)
    st.session_state.initialized = True


# ═══════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════

_init_app()
render()
