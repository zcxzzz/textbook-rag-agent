"""
PDF 教材摄入流水线 v2：
    递归发现 data/ 下所有 PDF → 多语种 Markdown 转换 → 智能分块 → Embedding → Chroma 持久化。
支持增量更新、页码元数据、语种标记、可配置的分块策略。
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

from tqdm import tqdm

from src.config import (
    DATA_DIR,
    INDEXES_DIR,
    SEMANTIC_CHUNK_THRESHOLD,
    get_embeddings,
    get_chroma_dir,
)
from src.utils import (
    find_pdfs,
    infer_book_name,
    pdf_to_text_chunks,
    extract_page_metadata,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")


# ── 分块策略 ────────────────────────────────────────────────
def split_markdown(md_text: str) -> list[str]:
    """两阶段智能分块：
    1. MarkdownHeaderTextSplitter — 按标题层级切分，保留结构。
    2. RecursiveCharacterTextSplitter — 对过长片段二次分割。
    """
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )

    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
        ("####", "h4"),
    ]

    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    md_docs = md_splitter.split_text(md_text)

    second_splitter = RecursiveCharacterTextSplitter(
        chunk_size=SEMANTIC_CHUNK_THRESHOLD,
        chunk_overlap=200,
        separators=["\n\n", "\n", "。", ".", "！", "!", "？", "?", " ", ""],
    )

    final_chunks: list[str] = []
    for doc in md_docs:
        if len(doc.page_content) > SEMANTIC_CHUNK_THRESHOLD:
            subs = second_splitter.split_text(doc.page_content)
            final_chunks.extend(subs)
        else:
            final_chunks.append(doc.page_content)

    logger.info("  分块完成: %d 个 chunk", len(final_chunks))
    return final_chunks


# ── 元数据构建 ──────────────────────────────────────────────
def build_metadata(
    book_name: str,
    chunk_text: str,
    chunk_index: int,
    source_path: Path,
    page_info: dict | None = None,
    page_language: str = "",
) -> dict:
    """为每个 chunk 生成丰富元数据。

    Args:
        book_name: 书名
        chunk_text: chunk 文本
        chunk_index: 此 PDF 中的序号
        source_path: 源 PDF 路径
        page_info: 来自 pymupdf4llm 的页面元数据 (page, page_label)
        page_language: 该页的语种检测结果
    """
    lines = chunk_text.strip().split("\n")
    heading = ""
    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            break

    meta = {
        "book_name": book_name,
        "source_file": source_path.name,
        "source_path": str(source_path),
        "chunk_index": chunk_index,
        "heading": heading or book_name,
        "char_count": len(chunk_text),
    }

    # 页码（1-based 显示更友好）
    if page_info:
        p = page_info.get("page", 0)
        meta["page"] = p
        meta["page_label"] = page_info.get("page_label", str(p + 1))

    # 语种
    if page_language:
        meta["language"] = page_language

    return meta


# ── 增量索引 ────────────────────────────────────────────────
def compute_file_hash(file_path: Path) -> str:
    """计算文件 SHA-256 哈希值。"""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def load_hash_map(book_name: str) -> dict[str, str]:
    """加载已索引文件的哈希映射表。"""
    hash_file = INDEXES_DIR / f".hash_{book_name}.json"
    if hash_file.exists():
        return json.loads(hash_file.read_text(encoding="utf-8"))
    return {}


def save_hash_map(book_name: str, hash_map: dict[str, str]) -> None:
    """保存已索引文件的哈希映射表。"""
    hash_file = INDEXES_DIR / f".hash_{book_name}.json"
    hash_file.write_text(
        json.dumps(hash_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════════
# 单本书摄入
# ═══════════════════════════════════════════════════════════════
def ingest_book(
    book_name: str,
    pdf_paths: list[Path],
    force: bool = False,
) -> int:
    """摄入一本书的所有 PDF，返回新增 chunk 数。"""
    from langchain_chroma import Chroma

    embeddings = get_embeddings()
    chroma_dir = get_chroma_dir(book_name)
    hash_map = {} if force else load_hash_map(book_name)
    total_chunks = 0
    failed_pdfs: list[str] = []

    vectorstore = Chroma(
        persist_directory=chroma_dir,
        embedding_function=embeddings,
    )

    for pdf_path in tqdm(pdf_paths, desc=f"📖 {book_name}", unit="pdf"):
        file_hash = compute_file_hash(pdf_path)

        # 增量跳过
        relative_key = str(pdf_path.relative_to(DATA_DIR))
        if not force and relative_key in hash_map:
            if hash_map[relative_key] == file_hash:
                logger.info("  ⏭ 跳过 (未变更): %s", pdf_path.name)
                continue

        # ── PDF → Markdown (page-level) ──
        try:
            page_chunks = pdf_to_text_chunks(pdf_path)
        except Exception:
            logger.exception("  解析失败，跳过: %s", pdf_path.name)
            failed_pdfs.append(pdf_path.name)
            continue

        # 后处理 + 语种检测
        page_chunks = extract_page_metadata(page_chunks)

        # 收集全文语种分布用于日志
        langs = {}
        for pc in page_chunks:
            lang = pc["metadata"].get("language", "")
            langs[lang] = langs.get(lang, 0) + 1
        logger.info("  📄 %s | %d 页 | 语种: %s",
                     pdf_path.name, len(page_chunks),
                     ", ".join(f"{k}({v})" for k, v in sorted(langs.items())))

        # ── 逐页分块 ──
        texts: list[str] = []
        metadatas: list[dict] = []
        ids: list[str] = []

        global_chunk_idx = 0
        for pc in page_chunks:
            page_text = pc["text"]
            page_meta = pc["metadata"]
            page_lang = page_meta.get("language", "")

            if not page_text.strip():
                continue

            # 按 Markdown 标题+递归切分
            chunks = split_markdown(page_text)

            for i, chunk in enumerate(chunks):
                texts.append(chunk)
                metadatas.append(build_metadata(
                    book_name, chunk, global_chunk_idx, pdf_path,
                    page_info=page_meta,
                    page_language=page_lang,
                ))
                ids.append(f"{book_name}_{pdf_path.stem}_p{page_meta.get('page', 0):04d}_chunk{global_chunk_idx:04d}")
                global_chunk_idx += 1

        # ── 批量写入 Chroma ──
        if texts:
            vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)
            total_chunks += len(texts)
            logger.info("  ✅ 摄入 %d chunks (来自 %d 页)", len(texts), len(page_chunks))

        # 更新哈希
        hash_map[relative_key] = file_hash

    save_hash_map(book_name, hash_map)

    if failed_pdfs:
        logger.warning("⚠️ %d 个 PDF 解析失败: %s", len(failed_pdfs), ", ".join(failed_pdfs))

    return total_chunks


# ── 入口 ────────────────────────────────────────────────────
def run_ingest(force: bool = False) -> None:
    """主入口：扫描 data/ → 按书名分组 → 依次摄入。"""
    logger.info("=" * 60)
    logger.info("Textbook-RAG-Agent v2 · 教材摄入流水线")
    logger.info("分块策略: RecursiveCharacterTextSplitter")
    logger.info("=" * 60)

    pdf_files = find_pdfs(DATA_DIR)
    if not pdf_files:
        logger.warning("未找到任何 PDF 文件！请将教材 PDF 放入 data/ 文件夹。")
        return

    # 按书名分组
    books: dict[str, list[Path]] = {}
    for pdf in pdf_files:
        book = infer_book_name(pdf, DATA_DIR)
        books.setdefault(book, []).append(pdf)

    logger.info("共发现 %d 本书，%d 个 PDF 文件", len(books), len(pdf_files))
    for book_name, paths in books.items():
        logger.info("  📚 %s: %d 个 PDF", book_name, len(paths))

    # 逐本摄入
    grand_total = 0
    for book_name, paths in books.items():
        n = ingest_book(book_name, paths, force=force)
        grand_total += n
        logger.info("🎉 %s 完成，新增 %d chunks", book_name, n)

    logger.info("=" * 60)
    logger.info("全部完成！总计新增 %d chunks", grand_total)
    logger.info("=" * 60)


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    run_ingest(force=force_flag)
