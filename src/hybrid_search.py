"""
混合搜索 — BM25 关键词检索 + 向量语义检索的 RRF 融合。
解决纯向量搜索在教科书专有名词、公式编号等精确匹配上的不足。
"""

import logging
from collections import defaultdict

from langchain_core.documents import Document

from src.config import (
    BM25_USE_JIEBA,
    HYBRID_VECTOR_WEIGHT,
)

logger = logging.getLogger("hybrid")


class BM25Index:
    """轻量级 BM25 关键词索引。

    基于 rank-bm25，支持 jieba 中文分词。
    在内存中构建，启动时从 Chroma 全量加载。
    """

    def __init__(self):
        self._bm25 = None
        self.documents: list[Document] = []
        self._tokenized_corpus: list[list[str]] = []

    def build(self, documents: list[Document]):
        """构建 BM25 索引。

        Args:
            documents: LangChain Document 列表
        """
        from rank_bm25 import BM25Okapi

        self.documents = documents
        self._tokenized_corpus = [self._tokenize(d.page_content) for d in documents]
        self._bm25 = BM25Okapi(self._tokenized_corpus)
        logger.info("BM25 索引构建完成: %d 篇文档", len(documents))

    def search(self, query: str, k: int = 20) -> list[tuple[Document, float]]:
        """BM25 搜索，返回 (Document, score) 列表。

        BM25 分数是未归一化的，仅在同一索引内可比。
        """
        if not self._bm25:
            return []

        tokenized = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized)

        # Top-K
        indexed = [(self.documents[i], scores[i])
                   for i in range(len(self.documents))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:k]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """分词：优先 jieba，回退按字符。"""
        if BM25_USE_JIEBA:
            try:
                import jieba
                return list(jieba.cut(text))
            except ImportError:
                pass
        # 按字符回退（中文逐字 + 英文按空格）
        import re
        tokens = []
        for part in re.split(r'(\s+)', text):
            if part.strip():
                # 中文字符逐字切
                has_cjk = bool(re.search(r'[一-鿿]', part))
                if has_cjk:
                    tokens.extend(list(part))
                else:
                    tokens.append(part)
        return tokens


class HybridSearcher:
    """混合搜索器：BM25 + 向量，RRF 融合。

    RRF(Reciprocal Rank Fusion):
        score(d) = Σ 1 / (k + rank_i(d))
        其中 k=60 是平滑常数

    最终得分:
        final = α * rrf_vector + (1-α) * rrf_bm25
    """

    def __init__(self, bm25_index: BM25Index,
                 vector_weight: float = HYBRID_VECTOR_WEIGHT,
                 rrf_k: int = 60):
        self.bm25_index = bm25_index
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k

    def search(self, query: str, vector_docs: list[Document],
               k: int = 8) -> list[Document]:
        """混合搜索。

        Args:
            query: 用户查询
            vector_docs: 向量检索结果（已按相关性排序）
            k: 返回文档数

        Returns:
            融合排序后的 Document 列表
        """
        # BM25 搜索
        bm25_results = self.bm25_index.search(query, k=max(k * 2, 20))

        if not bm25_results and not vector_docs:
            return []
        if not bm25_results:
            return vector_docs[:k]
        if not vector_docs:
            return [d for d, _ in bm25_results[:k]]

        # 构建 doc → rank 映射
        doc_to_rank_vector: dict[str, int] = {}
        doc_to_rank_bm25: dict[str, int] = {}
        doc_map: dict[str, Document] = {}

        def _doc_key(doc: Document) -> str:
            # 用 page_content 前 100 字符做 key（去空白标准化）
            return "".join(doc.page_content[:100].split())

        for rank, doc in enumerate(vector_docs, start=1):
            key = _doc_key(doc)
            doc_to_rank_vector[key] = rank
            doc_map[key] = doc

        for rank, (doc, _) in enumerate(bm25_results, start=1):
            key = _doc_key(doc)
            doc_to_rank_bm25[key] = rank
            if key not in doc_map:
                doc_map[key] = doc

        # RRF 融合
        all_keys = set(doc_to_rank_vector) | set(doc_to_rank_bm25)
        scores: dict[str, float] = {}

        for key in all_keys:
            rrf_v = (1.0 / (self.rrf_k + doc_to_rank_vector.get(key, 999)))
            rrf_b = (1.0 / (self.rrf_k + doc_to_rank_bm25.get(key, 999)))
            scores[key] = (self.vector_weight * rrf_v +
                           (1 - self.vector_weight) * rrf_b)

        # 排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = [doc_map[key] for key, _ in ranked[:k] if key in doc_map]

        logger.info("混合搜索: 向量%d + BM25%d → 融合后%d",
                     len(vector_docs), len(bm25_results), len(result))
        return result
