"""
配置中心：通过 .env 和预设字典管理 LLM、Embedding 及路径配置。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── 项目根目录 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 加载 .env ───────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

# ── 路径 ────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
INDEXES_DIR = PROJECT_ROOT / "indexes"

# ── 功能开关 ─────────────────────────────────────────────────
# 长期记忆 (SQLite)
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
MEMORY_DB_NAME = os.getenv("MEMORY_DB_NAME", "agent_memory.db")
MEMORY_DB_PATH = str(INDEXES_DIR / MEMORY_DB_NAME)
MEMORY_SUMMARY_MAX_MESSAGES = int(os.getenv("MEMORY_SUMMARY_MAX_MESSAGES", "40"))
MEMORY_AUTO_LEARNING_DETECTION = os.getenv("MEMORY_AUTO_LEARNING_DETECTION", "false").lower() == "true"

# RAG 检索增强
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "8"))
QUERY_EXPANSION_ENABLED = os.getenv("QUERY_EXPANSION_ENABLED", "true").lower() == "true"
QUERY_EXPANSION_MAX_SUBQUERIES = int(os.getenv("QUERY_EXPANSION_MAX_SUBQUERIES", "3"))
METADATA_FILTER_ENABLED = os.getenv("METADATA_FILTER_ENABLED", "true").lower() == "true"

# 混合搜索
HYBRID_SEARCH_ENABLED = os.getenv("HYBRID_SEARCH_ENABLED", "true").lower() == "true"
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.7"))
HYBRID_FETCH_K = int(os.getenv("HYBRID_FETCH_K", "20"))
HYBRID_FINAL_K = int(os.getenv("HYBRID_FINAL_K", "8"))
BM25_USE_JIEBA = os.getenv("BM25_USE_JIEBA", "true").lower() == "true"

# ── 检索参数 ─────────────────────────────────────────────────
RETRIEVER_K = int(os.getenv("RETRIEVER_K", "8"))
RETRIEVER_FETCH_K = int(os.getenv("RETRIEVER_FETCH_K", "20"))

# ── PDF 转换 ─────────────────────────────────────────────────
# 启用 page_chunks 模式可获取每页的精确页码
PDF_PAGE_CHUNKS = os.getenv("PDF_PAGE_CHUNKS", "true").lower() == "true"
# 文本后处理：清理 PDF 提取产生的空格断裂、页眉页脚等
PDF_POSTPROCESS = os.getenv("PDF_POSTPROCESS", "true").lower() == "true"
# 语种检测（标记 chunks 语言，中/英/日）
PDF_LANGUAGE_DETECTION = os.getenv("PDF_LANGUAGE_DETECTION", "true").lower() == "true"
# 字符阈值（超过此长度触发二次切分）
SEMANTIC_CHUNK_THRESHOLD = int(os.getenv("SEMANTIC_CHUNK_THRESHOLD", "3000"))

# ── Embedding 模型配置 ─────────────────────────────────────
# 支持的 provider: openai, deepseek, moonshot, zhipu, huggingface (本地免费)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "BAAI/bge-small-zh-v1.5",  # 中文小模型，~100MB，适合本地运行
)
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "512"))

# ── LLM 配置 ────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# ── Provider → Base URL & API Key 映射 ─────────────────────
PROVIDER_CONFIG = {
    "openai": {
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
    },
    "deepseek": {
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    },
    "moonshot": {
        "base_url": os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        "api_key": os.getenv("MOONSHOT_API_KEY", ""),
    },
    "zhipu": {
        "base_url": os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        "api_key": os.getenv("ZHIPU_API_KEY", ""),
    },
}


def get_llm():
    """根据配置创建 LangChain ChatModel 实例。"""
    from langchain_openai import ChatOpenAI

    llm_cfg = PROVIDER_CONFIG.get(LLM_PROVIDER)
    if not llm_cfg:
        raise ValueError(f"不支持的 LLM Provider: {LLM_PROVIDER}")

    if not llm_cfg["api_key"]:
        raise ValueError(
            f"缺少 {LLM_PROVIDER.upper()}_API_KEY，请在 .env 中配置"
        )

    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        openai_api_key=llm_cfg["api_key"],
        openai_api_base=llm_cfg["base_url"],
    )


def get_embeddings():
    """根据配置创建 Embeddings 实例。"""
    if EMBEDDING_PROVIDER == "huggingface":
        from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cuda"},
            encode_kwargs={"normalize_embeddings": True},
        )

    from langchain_openai import OpenAIEmbeddings

    emb_cfg = PROVIDER_CONFIG.get(EMBEDDING_PROVIDER)
    if not emb_cfg:
        raise ValueError(f"不支持的 Embedding Provider: {EMBEDDING_PROVIDER}")

    if not emb_cfg["api_key"]:
        raise ValueError(
            f"缺少 {EMBEDDING_PROVIDER.upper()}_API_KEY，请在 .env 中配置"
        )

    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=emb_cfg["api_key"],
        openai_api_base=emb_cfg["base_url"],
        dimensions=EMBEDDING_DIMENSIONS
        if EMBEDDING_PROVIDER == "openai"
        else None,
    )


def get_chroma_dir(book_name: str) -> str:
    """返回某本教材对应的 Chroma 持久化子目录路径。"""
    safe_name = book_name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    chroma_dir = INDEXES_DIR / safe_name
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return str(chroma_dir)
