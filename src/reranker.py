"""
Cross-Encoder 重排序器。
使用 sentence-transformers 对检索结果进行精排，提升教学相关性。
"""

import logging

logger = logging.getLogger("reranker")


class CrossEncoderReranker:
    """使用 BGE Reranker v2 M3 对检索文档重排序。

    特性：
    - 多语言支持（中英文）
    - 惰性加载（首次调用时下载模型 ~568MB）
    - 通过 RERANK_ENABLED 开关控制
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """惰性加载 sentence-transformers CrossEncoder。"""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info("正在加载重排序模型: %s", self.model_name)
            self._model = CrossEncoder(
                self.model_name,
                trust_remote_code=True,
            )
            logger.info("重排序模型加载完成")
        return self._model

    def rerank(self, query: str, documents: list, top_k: int = 8) -> list:
        """对文档列表按与查询的相关性重排序。

        Args:
            query: 用户查询
            documents: LangChain Document 列表
            top_k: 返回前 k 个文档

        Returns:
            重排序后的 Document 列表（可能少于输入）
        """
        if not documents:
            return []

        if len(documents) <= 1:
            return documents

        # 构造 (query, passage) 对
        pairs = [[query, doc.page_content[:2000]] for doc in documents]

        try:
            scores = self.model.predict(
                pairs,
                show_progress_bar=False,
            )
        except Exception:
            logger.exception("重排序预测失败，返回原始顺序")
            return documents[:top_k]

        # 按分数降序排列
        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        top_docs = [doc for doc, _ in scored[:top_k]]
        logger.info("重排序: %d → %d 文档", len(documents), len(top_docs))
        return top_docs
