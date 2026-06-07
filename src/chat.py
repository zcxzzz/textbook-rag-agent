"""
RAG 对话界面 — 教材私人导师 (v2)。
集成长期记忆、增强检索、混合搜索。
"""

import atexit
import logging
import sys
from pathlib import Path

from src.config import (
    INDEXES_DIR,
    LLM_MODEL,
    MEMORY_ENABLED,
    MEMORY_DB_PATH,
    get_chroma_dir,
    get_embeddings,
    get_llm,
)
from src.constants import HELP_TEXT, SEP, DSEP
from src.prompt_templates import build_system_prompt, build_compression_messages

COMPRESSION_INTERVAL = 20  # 每 N 轮对话触发一次压缩
COMPRESSION_KEEP_LAST = 10  # 压缩时保留最后 N 条消息（最近 5 轮）

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chat")


# ── 辅助 ──────────────────────────────────────────────────────
def list_available_books() -> list[str]:
    """列出已索引的教材。"""
    if not INDEXES_DIR.exists():
        return []
    return sorted(
        d.name for d in INDEXES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def select_book() -> str | None:
    """交互式选择教材。"""
    books = list_available_books()
    if not books:
        return None
    if len(books) == 1:
        return books[0]

    print("\n📚 已索引的教材：")
    for i, name in enumerate(books, 1):
        print(f"  [{i}] {name}")
    print("  [0] 全部教材")

    while True:
        try:
            choice = input("\n请选择教材 (输入编号): ").strip()
            idx = int(choice)
            if 0 <= idx <= len(books):
                return books[idx - 1] if idx > 0 else None
        except (ValueError, IndexError):
            pass
        print("输入无效，请重新输入。")


def load_vectorstore(book_name: str | None = None):
    """加载 Chroma 向量库（使用统一的路径清理）。"""
    from langchain_chroma import Chroma

    embeddings = get_embeddings()

    if book_name:
        chroma_dir = get_chroma_dir(book_name)
        if not Path(chroma_dir).exists():
            print(f"\n❌ 教材「{book_name}」尚未索引，请先运行 ingest.py")
            sys.exit(1)
        return Chroma(
            persist_directory=chroma_dir,
            embedding_function=embeddings,
        )

    # 全部教材：加载所有已索引的集合
    books = list_available_books()
    if not books:
        print("\n❌ 未找到任何已索引的教材，请先运行 ingest.py")
        sys.exit(1)

    # 返回第一个，EnhancedRetriever 会处理多集合
    chroma_dir = get_chroma_dir(books[0])
    return Chroma(
        persist_directory=chroma_dir,
        embedding_function=embeddings,
    )


def load_all_vectorstores():
    """加载所有已索引教材的向量库列表。"""
    from langchain_chroma import Chroma

    embeddings = get_embeddings()
    stores = []
    books = list_available_books()
    for book in books:
        chroma_dir = get_chroma_dir(book)
        try:
            store = Chroma(
                persist_directory=chroma_dir,
                embedding_function=embeddings,
            )
            stores.append((book, store))
        except Exception:
            logger.exception("加载向量库失败: %s", book)
    return stores


# ── 链构建 ────────────────────────────────────────────────────
def build_chain(book_name: str | None, agent_memory=None):
    """构建 RAG 对话链，集成增强检索。

    Args:
        book_name: 教材名（None = 全部）
        agent_memory: AgentMemory 实例（None = 无记忆）
    """
    from langchain_classic.chains import create_history_aware_retriever
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnableLambda

    llm = get_llm()

    # 增强检索器 — 用 RunnableLambda 包装以兼容 LCEL pipe 操作
    _raw_retriever = _build_retriever(book_name)
    retriever = RunnableLambda(lambda q, **kw: _raw_retriever.invoke(q))

    # 历史感知的查询重写
    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system", """根据对话历史，将用户的问题重新表述为一个独立的、完整的检索查询。
如果用户的问题已经足够独立，直接返回原问题。只返回重新表述的问题，不要加任何额外内容。"""),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_prompt
    )

    # 动态 System Prompt
    system_prompt = build_system_prompt(agent_memory, book_name)

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    qa_chain = create_stuff_documents_chain(llm, qa_prompt)
    return create_retrieval_chain(history_aware_retriever, qa_chain)


def _build_retriever(book_name: str | None):
    """构建检索器：优先使用 EnhancedRetriever，回退到基础 MMR。

    按照功能开关逐步启用各个阶段：
    - 阶段 2: EnhancedRetriever (元数据过滤 + 查询扩展 + 重排序)
    - 阶段 3: HybridSearcher (BM25 + RRF 融合)
    """
    from src.config import (
        RERANK_ENABLED,
        QUERY_EXPANSION_ENABLED,
        METADATA_FILTER_ENABLED,
        HYBRID_SEARCH_ENABLED,
    )

    # 尝试加载 EnhancedRetriever
    try:
        from src.retriever import EnhancedRetriever

        reranker = None
        if RERANK_ENABLED:
            try:
                from src.reranker import CrossEncoderReranker
                reranker = CrossEncoderReranker()
                logger.info("重排序器已加载")
            except Exception:
                logger.warning("重排序器加载失败，回退到无重排序模式")
                reranker = None

        return EnhancedRetriever(
            book_name=book_name,
            embeddings=get_embeddings(),
            reranker=reranker,
            enable_query_expansion=QUERY_EXPANSION_ENABLED,
            enable_metadata_filter=METADATA_FILTER_ENABLED,
            enable_hybrid=HYBRID_SEARCH_ENABLED,
        )
    except Exception:
        logger.warning("EnhancedRetriever 加载失败，回退到基础 MMR 检索器")
        vectorstore = load_vectorstore(book_name)
        return vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 8, "fetch_k": 20},
        )


# ── 记忆初始化 ────────────────────────────────────────────────
def _init_memory(resume_session_id: str | None = None):
    """初始化记忆系统。返回 (agent_memory, session_id, chat_history, book_name)。

    如果 resume_session_id 指定，重新打开该会话并在原会话上继续追加消息。
    """
    if not MEMORY_ENABLED:
        return None, "", [], None

    try:
        from src.memory import AgentMemory
        memory = AgentMemory(MEMORY_DB_PATH, llm_factory=get_llm)

        loaded_history: list[dict] = []
        resumed_book: str | None = None

        if resume_session_id:
            session_info = memory.reopen_session(resume_session_id)
            if session_info:
                loaded_history = memory.get_session_messages(resume_session_id, limit=100)
                resumed_book = session_info.get("book_name")
                if loaded_history:
                    logger.info("已恢复会话 %s 的 %d 条消息", resume_session_id[:8], len(loaded_history))
                session_id = resume_session_id
                atexit.register(lambda: _cleanup_memory(memory, session_id))
                return memory, session_id, loaded_history, resumed_book
            else:
                logger.warning("会话 %s 不存在，将创建新会话", resume_session_id)

        # 全新会话
        session_id = memory.create_session(None)
        atexit.register(lambda: _cleanup_memory(memory, session_id))
        return memory, session_id, loaded_history, resumed_book
    except Exception:
        logger.exception("记忆系统初始化失败，继续运行但不保存历史")
        return None, "", [], None


def _cleanup_memory(agent_memory, session_id: str):
    """退出时的清理：关闭会话生成摘要，打印 session ID。"""
    try:
        if agent_memory and session_id:
            agent_memory.close_session(session_id)
            agent_memory.close()
            print(f"\n📝 会话已保存  ID: {session_id}")
            print(f"   下次恢复: python -m src.chat --session {session_id}")
    except Exception:
        pass


# ── 对话循环 ──────────────────────────────────────────────────
def run_chat(book_name: str | None = None, session_id: str | None = None):
    """启动对话循环。

    Args:
        book_name: 指定教材名（None = 交互选择）
        session_id: 恢复指定会话的上下文（None = 全新对话）
    """
    print(f"""
{SEP}
╔{'═' * 58}╗
║  📖  Textbook-RAG-Agent v2 · 教材私人导师                ║
║  模型: {LLM_MODEL:<47}║
╙{'═' * 58}╜
{SEP}
""")

    # 检查教材
    books = list_available_books()
    if not books:
        print("❌ 未找到已索引的教材。请先运行: python -m src.ingest")
        sys.exit(1)

    if session_id:
        print(f"🔄 恢复会话: {session_id}")

    # 如果恢复会话且未指定教材，先跳过选择（后续从会话记录中获取）
    if book_name is None and not session_id:
        book_name = select_book()

    if book_name:
        print(f"📖 当前教材: {book_name}")

    # 初始化记忆（含恢复历史）
    agent_memory, session_id, loaded_history, resumed_book = _init_memory(session_id)

    # 恢复会话时，优先使用原会话的教材
    if resumed_book and book_name is None:
        book_name = resumed_book
        print(f"📖 当前教材: {book_name}")

    # 此时仍无教材则交互选择
    if book_name is None:
        book_name = select_book()
        if book_name:
            print(f"📖 当前教材: {book_name}")

    if agent_memory:
        agent_memory.conn.execute(
            "UPDATE sessions SET book_name = ? WHERE session_id = ?",
            (book_name, session_id),
        )
        agent_memory.conn.commit()

    chat_history: list[dict] = loaded_history
    round_count = len(loaded_history) // 2  # 已完成的对话轮数
    if loaded_history:
        print(f"\n📝 已恢复 {len(loaded_history)} 条历史消息（会话: {session_id}）\n")

    print("💡 输入 /help 查看可用命令\n")

    # 构建链
    print("⏳ 正在加载模型、向量库和检索器...")
    try:
        chain = build_chain(book_name, agent_memory)
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        if agent_memory:
            agent_memory.close_session(session_id)
            agent_memory.close()
        sys.exit(1)
    print("✅ 就绪！开始学习吧。\n")

    from src.commands import handle_command

    while True:
        try:
            user_input = input("👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        # 命令
        if user_input.startswith("/"):
            should_exit, output = handle_command(
                user_input, chain, chat_history,
                agent_memory=agent_memory,
                session_id=session_id,
                book_name=book_name,
            )
            print(f"\n🤖 导师:\n{output}\n")
            if should_exit:
                break
            continue

        # 正常 RAG 对话
        try:
            print("\n⏳ 正在检索教材并生成回答...")
            result = chain.invoke({
                "input": user_input,
                "chat_history": chat_history,
            })
            answer = result["answer"]

            # 来源（含页码）
            sources = set()
            for doc in result.get("context", []):
                src = doc.metadata.get("source_file", "")
                heading = doc.metadata.get("heading", "")
                page = doc.metadata.get("page_label") or doc.metadata.get("page")
                if src:
                    parts = [f"  📍 {src}"]
                    if page is not None:
                        try:
                            p = int(page)
                            parts.append(f"p{p + 1}" if p < 1000 else f"p{p}")
                        except (ValueError, TypeError):
                            parts.append(f"p{page}")
                    if heading:
                        parts.append(f"→ {heading}")
                    sources.add(" ".join(parts))
                    # 如果有 heading 也可单独加一条不含 page 的版本作为去重后备


            print(f"\n🤖 导师:\n{answer}\n")
            if sources:
                shown = sorted(sources)[:5]
                print("📚 参考来源:\n" + "\n".join(shown) + "\n")

            # 更新历史
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": answer})

            # 持久化消息
            if agent_memory and session_id:
                source_dicts = [
                    {"source_file": doc.metadata.get("source_file", ""),
                     "heading": doc.metadata.get("heading", ""),
                     "book_name": doc.metadata.get("book_name", "")}
                    for doc in result.get("context", [])
                ]
                agent_memory.add_message(session_id, "user", user_input)
                agent_memory.add_message(
                    session_id, "assistant", answer, sources=source_dicts[:5]
                )

            # 自动检测学习内容
            if agent_memory and MEMORY_ENABLED and session_id and book_name:
                _auto_detect_learning(agent_memory, session_id, book_name,
                                      user_input, answer)

            # 上下文压缩检查
            round_count += 1
            if round_count > 0 and round_count % COMPRESSION_INTERVAL == 0:
                print("\n🗜️  正在压缩对话上下文...")
                _compress_history(chat_history, round_count)
                print(f"   当前上下文: {len(chat_history)} 条消息\n")

        except Exception as e:
            logger.exception("对话出错")
            print(f"\n❌ 出错了: {e}\n")


def _compress_history(chat_history: list[dict], round_count: int) -> list[dict]:
    """压缩对话历史：将旧消息替换为结构化摘要，保留最近几轮完整对话。

    Returns:
        压缩后的 chat_history（原地修改并返回）
    """
    if len(chat_history) <= COMPRESSION_KEEP_LAST + 4:
        return chat_history  # 消息太少，不压缩

    logger.info("触发上下文压缩（第 %d 轮）", round_count)

    # 保留最后 K 条消息，压缩前面的
    split_at = len(chat_history) - COMPRESSION_KEEP_LAST
    to_compress = chat_history[:split_at]
    recent = chat_history[split_at:]

    try:
        llm = get_llm()
        msgs = build_compression_messages(to_compress)
        resp = llm.invoke(msgs)
        summary = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()

        # 用摘要消息替换压缩部分
        compressed = [{"role": "user", "content": f"[上下文摘要]\n{summary}"}]
        chat_history.clear()
        chat_history.extend(compressed + recent)

        logger.info("压缩完成: %d 条消息 → 摘要 + %d 条（节省约 %d tokens）",
                     len(to_compress), len(recent), len(to_compress) * 80)
    except Exception:
        logger.exception("压缩失败，保留原历史")

    return chat_history


def _auto_detect_learning(agent_memory, session_id: str, book_name: str,
                          question: str, answer: str):
    """从对话中自动检测学习主题并记录。"""
    from src.config import MEMORY_AUTO_LEARNING_DETECTION
    if not MEMORY_AUTO_LEARNING_DETECTION:
        return
    try:
        import re
        # 简单启发式：提取可能的概念名
        patterns = [
            r'什么是[「「](.+?)[」」]',
            r'什么是(.{2,20}?)[？?]',
            r'讲解(.{2,20}?)[。]',
            r'(?:概念|定义|定理)[：:]\s*(.{2,20})',
        ]
        topic = None
        for pattern in patterns:
            m = re.search(pattern, question)
            if m:
                topic = m.group(1).strip()[:80]
                break
        # 没匹配到模式就用提问本身作为 topic
        if not topic:
            clean = question.strip()
            # 去掉常见问句前缀
            for prefix in ['请问', '问一下', '我想知道', '告诉我', '解释一下']:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
            topic = clean.strip()[:80]
        if topic:
            # 尝试提取章节号
            chapter = "自动检测"
            ch_m = re.search(r'第\s*(\d+)\s*课', question)
            if ch_m:
                chapter = f"第{ch_m.group(1)}课"
            else:
                ch_m = re.search(r'第\s*(\d+)\s*章', question)
                if ch_m:
                    chapter = f"第{ch_m.group(1)}章"
            agent_memory.record_learning(
                session_id, book_name, chapter, topic, 1
            )
    except Exception:
        pass


# ── 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    book = None
    session_id = None
    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
        elif args[i].startswith("--session="):
            session_id = args[i].split("=", 1)[1]
            i += 1
        elif not args[i].startswith("-"):
            book = args[i]
            i += 1
        else:
            i += 1
    run_chat(book, session_id=session_id)
