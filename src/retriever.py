"""
增强检索器 — 元数据过滤 + 查询扩展 + 多集合合并 + 混合搜索支持。
LangChain 兼容（实现 invoke / get_relevant_documents）。
"""

import logging
import re
from pathlib import Path

from langchain_core.documents import Document

from src.config import (
    INDEXES_DIR,
    HYBRID_FETCH_K,
    HYBRID_FINAL_K,
    QUERY_EXPANSION_MAX_SUBQUERIES,
    RETRIEVER_K,
    RETRIEVER_FETCH_K,
    get_chroma_dir,
    get_embeddings,
    get_llm,
)

logger = logging.getLogger("retriever")

def _cn_to_arabic_chapter(m: re.Match) -> str:
    """中文数字章节转阿拉伯数字。"""
    cn_map = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
              '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
    return f"第{cn_map.get(m.group(1), m.group(1))}章"


# ── 章节引用正则 ─────────────────────────────────────────────
CHAPTER_PATTERNS = [
    (re.compile(r'第\s*(\d+)\s*章'), lambda m: f"第{m.group(1)}章"),
    (re.compile(r'第\s*([一二三四五六七八九十]+)\s*章'), _cn_to_arabic_chapter),
    (re.compile(r'[Ss]ection\s+(\d+\.?\d*)'), lambda m: f"Section {m.group(1)}"),
    (re.compile(r'章节\s*(\d+\.?\d*)'), lambda m: f"第{m.group(1)}章"),
    (re.compile(r'[Cc]hapter\s+(\d+)'), lambda m: f"Chapter {m.group(1)}"),
]


def parse_chapter_hint(query: str) -> str | None:
    """从用户查询中提取章节引用。

    Returns:
        规范化后的章节标识符，如 "第3章"、"Section 2.1"，或 None
    """
    for pattern, formatter in CHAPTER_PATTERNS:
        m = pattern.search(query)
        if m:
            return formatter(m)
    return None


# ═══════════════════════════════════════════════════════════════
class EnhancedRetriever:
    """增强检索器 — 企业级 RAG 检索流水线。

    流水线：
    query → parse_chapter_hint → expand_query → [per subQ]:
        → (hybrid_search | mmr_vector_search)
        → metadata_filter(by chapter)
    → merge + dedup → rerank → top_k

    LangChain 兼容：实现 invoke(input) → list[Document]
    """

    def __init__(
        self,
        book_name: str | None,
        embeddings,
        reranker=None,
        enable_query_expansion: bool = True,
        enable_metadata_filter: bool = True,
        enable_hybrid: bool = True,
    ):
        self.book_name = book_name
        self.embeddings = embeddings
        self.reranker = reranker
        self.enable_query_expansion = enable_query_expansion
        self.enable_metadata_filter = enable_metadata_filter
        self.enable_hybrid = enable_hybrid

        self._stores: list | None = None
        self._chapter_headings_cache: dict[str, list[str]] = {}
        self._hybrid_searcher = None

    # ── 集合加载 ──────────────────────────────────────────
    @property
    def stores(self) -> list:
        """加载向量库（惰性）。"""
        if self._stores is None:
            self._stores = self._load_stores()
        return self._stores

    def _load_stores(self) -> list:
        """加载指定书籍或全部书籍的 Chroma 集合。"""
        from langchain_chroma import Chroma

        books = _list_available_books()
        stores = []

        if self.book_name:
            chroma_dir = get_chroma_dir(self.book_name)
            if Path(chroma_dir).exists():
                store = Chroma(
                    persist_directory=chroma_dir,
                    embedding_function=self.embeddings,
                )
                stores.append((self.book_name, store))
        else:
            for book in books:
                chroma_dir = get_chroma_dir(book)
                try:
                    store = Chroma(
                        persist_directory=chroma_dir,
                        embedding_function=self.embeddings,
                    )
                    stores.append((book, store))
                except Exception:
                    logger.exception("加载集合失败: %s", book)

        logger.info("已加载 %d 个向量库", len(stores))
        return stores

    # ── 元数据缓存 ────────────────────────────────────────
    def _get_chapter_headings(self, book_name: str) -> list[str]:
        """获取某本书的所有已知章节标题。"""
        if book_name not in self._chapter_headings_cache:
            store_dict = {b: s for b, s in self.stores}
            if book_name in store_dict:
                try:
                    data = store_dict[book_name].get(
                        include=["metadatas"], limit=0
                    )
                    # Chroma get() returns different structures — handle both
                    if "metadatas" in data and data["metadatas"]:
                        headings = set()
                        for m in data["metadatas"]:
                            if isinstance(m, dict) and "heading" in m:
                                headings.add(m["heading"])
                        self._chapter_headings_cache[book_name] = list(headings)
                    else:
                        self._chapter_headings_cache[book_name] = []
                except Exception:
                    # Fallback: collect headings from retrieval results
                    self._chapter_headings_cache[book_name] = []
                    logger.debug("无法预加载标题缓存: %s", book_name)
        return self._chapter_headings_cache.get(book_name, [])

    # ── 查询扩展 ──────────────────────────────────────────
    def _expand_query(self, query: str) -> list[str]:
        """将复杂问题拆解为子查询。"""
        if not self.enable_query_expansion:
            return [query]

        # 简单查询不拆
        if len(query) < 20 or "?" not in query and "？" not in query:
            return [query]

        try:
            llm = get_llm()
            prompt = f"""将以下学习问题拆成 2-3 个独立的、可用于向量检索的子问题。
每个子问题一行。如果问题本身很简单无需拆分，直接返回原问题。

原始问题：{query}

子问题（每行一个）："""
            resp = llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
            sub_queries = [q.strip() for q in text.strip().split("\n")
                          if q.strip() and q.strip() != query]
            if not sub_queries:
                return [query]
            result = sub_queries[:QUERY_EXPANSION_MAX_SUBQUERIES]
            logger.info("查询扩展: %d 个子查询", len(result))
            return result
        except Exception:
            logger.exception("查询扩展失败")
            return [query]

    # ── 混合搜索初始化 ────────────────────────────────────
    def _init_hybrid_searcher(self):
        """初始化混合搜索器（BM25 + 向量融合）。"""
        if self._hybrid_searcher is not None:
            return
        if not self.enable_hybrid:
            return
        try:
            from src.hybrid_search import HybridSearcher, BM25Index
            # 从所有集合加载文档
            all_docs = []
            for _, store in self.stores:
                try:
                    data = store.get(include=["documents", "metadatas"])
                    if data.get("documents"):
                        for i, text in enumerate(data["documents"]):
                            meta = data["metadatas"][i] if data.get("metadatas") and i < len(data["metadatas"]) else {}
                            all_docs.append(Document(page_content=text, metadata=meta))
                except Exception:
                    logger.exception("混合搜索数据加载失败")
            if all_docs:
                bm25 = BM25Index()
                bm25.build(all_docs)
                self._hybrid_searcher = HybridSearcher(bm25)
                logger.info("混合搜索已就绪: %d 篇文档", len(all_docs))
        except Exception:
            logger.exception("混合搜索初始化失败")
            self._hybrid_searcher = None

    # ── 核心检索 ──────────────────────────────────────────
    def _retrieve_from_stores(self, query: str, k: int = 20) -> list[Document]:
        """从所有已加载集合检索。支持混合搜索。"""
        if self.enable_hybrid and self._hybrid_searcher is None:
            self._init_hybrid_searcher()

        all_results: list[Document] = []
        seen = set()

        for book_name, store in self.stores:
            if self.enable_hybrid and self._hybrid_searcher:
                # 混合搜索：需要向量候选
                try:
                    vector_docs = store.similarity_search_with_relevance_scores(
                        query, k=HYBRID_FETCH_K,
                    )
                    self._hybrid_searcher.bm25_index.documents = [
                        Document(page_content=d[0].page_content,
                                 metadata=d[0].metadata)
                        for d in vector_docs
                    ]
                except Exception:
                    vector_docs = []

                try:
                    docs = self._hybrid_searcher.search(
                        query,
                        vector_docs=[d[0] for d in vector_docs] if vector_docs else [],
                        k=k,
                    )
                except Exception:
                    try:
                        docs = store.similarity_search(query, k=k)
                    except Exception:
                        continue
            else:
                # 纯向量 MMR
                try:
                    docs = store.max_marginal_relevance_search(
                        query, k=k, fetch_k=RETRIEVER_FETCH_K,
                    )
                except Exception:
                    try:
                        docs = store.similarity_search(query, k=k)
                    except Exception:
                        continue

            for doc in docs:
                key = doc.page_content[:120]
                if key not in seen:
                    seen.add(key)
                    all_results.append(doc)

        return all_results

    def retrieve(self, query: str, k: int = 8) -> list[Document]:
        """完整的增强检索流水线。

        1. 解析章节引用
        2. 查询扩展
        3. 多集合检索 + 元数据过滤
        4. 合并去重
        5. 重排序
        6. 返回 top_k
        """
        chapter_hint = parse_chapter_hint(query) if self.enable_metadata_filter else None
        if chapter_hint:
            logger.info("检测到章节引用: %s", chapter_hint)

        sub_queries = self._expand_query(query)

        all_results: list[Document] = []
        seen = set()

        for sub_q in sub_queries:
            docs = self._retrieve_from_stores(sub_q, k=RETRIEVER_FETCH_K)

            # 元数据过滤：如果指定了章节，过滤 heading 包含章节的文档
            if chapter_hint:
                filtered = []
                for doc in docs:
                    heading = doc.metadata.get("heading", "")
                    if _heading_matches_chapter(heading, chapter_hint):
                        filtered.append(doc)
                if filtered:
                    docs = filtered
                else:
                    # 严格模式：如果没匹配到，保留原始结果以免空返回
                    logger.debug("章节过滤无匹配，回退到全部结果")
                    # 尝试模糊匹配
                    chapter_num = re.search(r'(\d+)', chapter_hint)
                    if chapter_num:
                        cn = chapter_num.group(1)
                        fuzzy = [d for d in docs
                                 if cn in d.metadata.get("heading", "")
                                 or cn in d.metadata.get("source_file", "")]
                        if fuzzy:
                            docs = fuzzy

            for doc in docs:
                key = doc.page_content[:120]
                if key not in seen:
                    seen.add(key)
                    all_results.append(doc)

        # 重排序：先预过滤到 30 控制显存峰值
        if self.reranker and len(all_results) > 1:
            pre_filter = all_results[:30]
            all_results = self.reranker.rerank(query, pre_filter, top_k=k * 2)

        # 截断
        final = all_results[:k]
        logger.info("检索完成: %d 个文档（来自 %d 候选）", len(final), len(all_results))
        return final

    # ── LangChain 接口 ────────────────────────────────────
    def invoke(self, input_text: str, **kwargs) -> list[Document]:
        """LangChain BaseRetriever 兼容接口。"""
        k = kwargs.pop("k", RETRIEVER_K)
        return self.retrieve(input_text, k=k)

    def get_relevant_documents(self, query: str, **kwargs) -> list[Document]:
        """LangChain 旧版接口兼容。"""
        return self.retrieve(query)


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _list_available_books() -> list[str]:
    """列出已索引的教材名。"""
    if not INDEXES_DIR.exists():
        return []
    return sorted(
        d.name for d in INDEXES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def _heading_matches_chapter(heading: str, chapter_hint: str) -> bool:
    """检查 heading 是否匹配章节引用。

    示例:
        heading="## 第3章 导数"  chapter_hint="第3章" → True
        heading="## Chapter 5"   chapter_hint="第5章" → True
        heading="## Section 2.1" chapter_hint="Section 2.1" → True
    """
    if not heading or not chapter_hint:
        return False

    heading_lower = heading.lower().replace(" ", "")
    hint_lower = chapter_hint.lower().replace(" ", "")

    if hint_lower in heading_lower:
        return True

    # 阿拉伯数字交叉匹配: "Chapter 3" vs "第3章"
    hint_num = re.search(r'(\d+)', hint_lower)
    if hint_num:
        num = hint_num.group(1)
        if num in heading_lower:
            # 放宽匹配：可能 heading 是 "### Chapter 3" 而 hint 是 "第3章"
            # 但也排除 false positive 如 "公式3.5"
            heading_num = re.search(r'(\d+)', heading_lower)
            if heading_num and heading_num.group(1) == num:
                # 确保上下文是章节而非公式
                context = heading_lower
                if any(kw in context for kw in ('chapter', 'ch', '节', '章')):
                    return True

    return False
