"""
PDF 解析工具 — 多语种支持（中/英/日）+ 扫描版 OCR 回退。
主入口：pdf_to_text_chunks() — 自动检测并选择最佳提取路径。
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 语种检测 ─────────────────────────────────────────────────
_CJK_UNIFIED = re.compile(r'[一-鿿]')
_JP_KANA = re.compile(r'[぀-ゟ゠-ヿ]')
_LATIN = re.compile(r'[a-zA-Z]')


def detect_language(text: str) -> str:
    """检测文本主要语种。返回 'zh', 'ja', 'en', 'mixed', 'unknown'。"""
    total = len(text)
    if total == 0:
        return "unknown"

    cjk_count = len(_CJK_UNIFIED.findall(text))
    kana_count = len(_JP_KANA.findall(text))
    latin_count = len(_LATIN.findall(text))

    if kana_count > 5:
        return "ja"
    if cjk_count > total * 0.15:
        if latin_count > total * 0.2 and cjk_count > total * 0.1:
            return "mixed"
        return "zh"
    if latin_count > total * 0.4:
        if cjk_count > total * 0.05:
            return "mixed"
        return "en"
    return "mixed"


# ── 文本清洗 ─────────────────────────────────────────────────
def clean_markdown_text(md_text: str) -> str:
    """后处理 PDF 提取的文本：清理 PDF 排版引擎的常见噪声。

    具体修复：
    - CJK 字符间的多余空格
    - 英文连字符断词
    - 连续空行压缩
    - Unicode 控制字符/零宽字符
    - CJK+标点间的多余空格
    """
    if not md_text:
        return md_text

    # BOM + 零宽字符
    for char in ('﻿', '​', '‌', '‍', '⁠'):
        md_text = md_text.replace(char, '')

    # 制表符 → 空格
    md_text = re.sub(r'[\t\v\f\r]+', ' ', md_text)

    # CJK 字符间空格 → 删除
    md_text = re.sub(
        r'(?<=[一-鿿぀-ゟ゠-ヿ])\s+'
        r'(?=[一-鿿぀-ゟ゠-ヿ])',
        '', md_text,
    )

    # CJK + 标点间空格 → 删除
    md_text = re.sub(
        r'(?<=[一-鿿぀-ゟ゠-ヿ])\s+(?=[。，、；：！？」』）\)】])',
        '', md_text,
    )

    # 英文断词连字符
    md_text = re.sub(r'(\w)-\n(\w)', r'\1\2', md_text)

    # 同段内换行合并（保留标题/列表/表格行）
    lines = md_text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if (not stripped or
                stripped.startswith('#') or
                stripped.startswith('- ') or stripped.startswith('* ') or
                stripped.startswith('|') or
                re.match(r'^\d+[\.\)]\s', stripped)):
            cleaned.append(line.rstrip())
        else:
            if cleaned and cleaned[-1] and not cleaned[-1].startswith('#'):
                cleaned[-1] = cleaned[-1].rstrip() + ' ' + stripped
            else:
                cleaned.append(stripped)
    md_text = '\n'.join(cleaned)

    # 压缩过多空行
    md_text = re.sub(r'\n{4,}', '\n\n\n', md_text)

    return md_text.strip()


# ═══════════════════════════════════════════════════════════════
# PDF 文本提取 — 自动选择最佳路径
# ═══════════════════════════════════════════════════════════════

def _pdf_has_text(pdf_path: Path, sample_pages: int = 3) -> bool:
    """检查 PDF 是否有可提取的文本层（非纯扫描版）。

    抽样前几页，用 pymupdf 底层 API 直接提取文本。
    如果所有抽样页都为空 → 扫描版 PDF。
    """
    import fitz  # pymupdf
    doc = fitz.open(str(pdf_path))
    pages_to_check = min(sample_pages, doc.page_count)
    text_found = False

    for i in range(pages_to_check):
        text = doc[i].get_text("text")
        if text and len(text.strip()) > 20:
            text_found = True
            break

    doc.close()
    return text_found


def _pdf_to_markdown_direct(pdf_path: Path) -> list[dict]:
    """使用 pymupdf4llm 的标准路径提取文本。

    适合有文本层的正常 PDF。加 force_text=True 解决透明文本问题。
    """
    import pymupdf4llm

    logger.info("  [标准提取] %s", pdf_path.name)
    chunks = pymupdf4llm.to_markdown(
        str(pdf_path),
        page_chunks=True,
        write_images=False,
        embed_images=False,
        force_text=True,          # ← 关键：不跳过透明文本
        show_progress=False,
    )
    return chunks


def _pdf_page_to_image(page_index: int, pdf_path: Path, dpi: int = 200):
    """用 PyMuPDF 将单页渲染为 PIL Image（无需 poppler）。"""
    from PIL import Image
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def _pdf_to_markdown_ocr(pdf_path: Path) -> list[dict]:
    """OCR 路径：用 PyMuPDF 逐页渲染 → PaddleOCR 识别。

    支持中/英/日混合文本，纯 Python 调用，无需 poppler/Tesseract 等系统依赖。
    首次运行自动下载 PaddleOCR 模型（~100MB，含中/英/日）。
    """
    import numpy as np

    logger.info("  [OCR 提取] %s (PaddleOCR)", pdf_path.name)

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise ImportError(
            "PDF 是扫描版，需要安装 PaddleOCR：\n"
            "  pip install paddlepaddle paddleocr\n"
        )

    page_count = _count_pdf_pages(pdf_path)
    logger.info("  共 %d 页，正在用 PyMuPDF 渲染 + PaddleOCR 识别...", page_count)

    # 初始化 OCR 模型（use_gpu=True 利用 CUDA 加速）
    ocr_ch = None
    ocr_jp = None
    try:
        ocr_ch = PaddleOCR(lang='ch', use_gpu=True)
        logger.info("  PaddleOCR 中英文模型就绪 (GPU)")
    except Exception as e:
        logger.warning("  PaddleOCR 中英文模型加载失败: %s", e)

    try:
        ocr_jp = PaddleOCR(lang='japan', use_gpu=True)
        logger.info("  PaddleOCR 日文模型就绪 (GPU)")
    except Exception as e:
        logger.warning("  PaddleOCR 日文模型加载失败（将仅用中英模型）: %s", e)

    chunks: list[dict] = []
    for i in range(page_count):
        try:
            img = _pdf_page_to_image(i, pdf_path, dpi=200)
        except Exception as e:
            logger.warning("  第 %d 页渲染失败: %s", i + 1, e)
            continue

        img_array = np.array(img)
        text_lines: list[str] = []

        # 中英文识别（PaddleOCR 2.x: result = [[[bbox, (text, conf)], ...]]）
        if ocr_ch is not None:
            try:
                result = ocr_ch.ocr(img_array)
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            txt = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                            if txt.strip():
                                text_lines.append(txt.strip())
            except Exception:
                pass

        # 日文补充识别（仅当主模型识别到极少文本时触发）
        if ocr_jp is not None and len(text_lines) < 3:
            try:
                result = ocr_jp.ocr(img_array)
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            txt = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                            if txt.strip():
                                text_lines.append(txt.strip())
            except Exception:
                pass

        if text_lines:
            page_text = "\n".join(text_lines)
            chunks.append({
                "metadata": {
                    "page": i,
                    "page_label": str(i + 1),
                    "extraction_method": "ocr_paddle",
                },
                "text": page_text,
            })

        if (i + 1) % 10 == 0:
            logger.info("  OCR 进度: %d/%d 页", i + 1, page_count)

    logger.info("  OCR 完成: %d/%d 页有文本", len(chunks), page_count)
    return chunks


def _count_pdf_pages(pdf_path: Path) -> int:
    import fitz
    doc = fitz.open(str(pdf_path))
    count = doc.page_count
    doc.close()
    return count


def pdf_to_text_chunks(pdf_path: str | Path) -> list[dict]:
    """PDF → 结构化文本（自动选择最佳提取路径）。

    策略：
    1. 先用 pymupdf4llm 标准路径（带 force_text=True）
    2. 如果结果为空或几乎为空，检查是否是扫描版
    3. 如果是扫描版 → 走 OCR 路径
    4. 如果标准路径部分页面为空 → 保留有文本的页面，用 pymupdf 直接提取补充空白页

    Returns:
        [{"metadata": {page, page_label, language, ...}, "text": "markdown"}, ...]
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    total_pages = _count_pdf_pages(pdf_path)
    logger.info("正在解析 PDF: %s (%.1f MB, %d 页)", pdf_path.name, file_size_mb, total_pages)

    # ── 路径 1: 先检测是否有文本层（避免在扫描版 PDF 上浪费时间）──
    has_text = _pdf_has_text(pdf_path)
    if not has_text:
        logger.warning("  扫描版 PDF（无文本层），直接切换到 OCR 路径。")
        return _pdf_to_markdown_ocr(pdf_path)

    # ── 路径 2: pymupdf4llm 标准提取 ──
    chunks = _pdf_to_markdown_direct(pdf_path)

    # 统计有效文本
    total_chars = sum(len(c.get("text", "")) for c in chunks)
    non_empty_pages = sum(1 for c in chunks if c.get("text", "").strip())
    logger.info("  标准提取: %d 页有文本, 总计 %d 字符", non_empty_pages, total_chars)

    # ── 路径 3: 如果几乎全是空页 → 回退 ──
    if non_empty_pages == 0 or (non_empty_pages < total_pages * 0.1 and total_chars < 500):
        logger.info("  pymupdf4llm 提取文本有限，尝试直接 pymupdf 提取...")
        return _fallback_pymupdf_direct(pdf_path)

    # ── 路径 4: 部分空页 → 逐页补全 ──
    if non_empty_pages < total_pages * 0.8:
        logger.info("  %d/%d 页为空，使用 pymupdf 直接补全空页", total_pages - non_empty_pages, total_pages)
        chunks = _fill_empty_pages(pdf_path, chunks)

    logger.info("  PDF 解析完成: %d 页, 总计 %d 字符",
                len([c for c in chunks if c.get("text", "").strip()]),
                sum(len(c.get("text", "")) for c in chunks))

    if not chunks:
        raise ValueError(f"PDF 无法提取任何文本: {pdf_path.name}")

    return chunks


def _fallback_pymupdf_direct(pdf_path: Path) -> list[dict]:
    """用 pymupdf 直接提取文本（pymupdf4llm 失败时的回退）。"""
    import fitz
    doc = fitz.open(str(pdf_path))
    chunks = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text")
        if text and text.strip():
            chunks.append({
                "metadata": {
                    "page": i,
                    "page_label": str(i + 1),
                    "extraction_method": "pymupdf_direct",
                },
                "text": text,
            })
    doc.close()
    return chunks


def _fill_empty_pages(pdf_path: Path, existing_chunks: list[dict]) -> list[dict]:
    """用 pymupdf.get_text() 补全 pymupdf4llm 中为空的页面。"""
    import fitz

    # 构建已有页面集合
    existing_pages = {c["metadata"].get("page", -1) for c in existing_chunks}

    doc = fitz.open(str(pdf_path))
    for i in range(doc.page_count):
        if i in existing_pages:
            continue
        text = doc[i].get_text("text")
        if text and text.strip():
            existing_chunks.append({
                "metadata": {
                    "page": i,
                    "page_label": str(i + 1),
                    "extraction_method": "pymupdf_fill",
                },
                "text": text,
            })
    doc.close()
    return existing_chunks


# ═══════════════════════════════════════════════════════════════
# 后处理
# ═══════════════════════════════════════════════════════════════

def extract_page_metadata(chunks: list[dict]) -> list[dict]:
    """为每个页面 chunk 附加语种、文本统计等元数据。"""
    from src.config import PDF_LANGUAGE_DETECTION, PDF_POSTPROCESS

    enhanced = []
    for ch in chunks:
        text = ch["text"]
        meta = dict(ch.get("metadata", {}))

        if PDF_POSTPROCESS:
            text = clean_markdown_text(text)

        if not text.strip():
            continue

        if PDF_LANGUAGE_DETECTION:
            meta["language"] = detect_language(text)

        meta["char_count"] = len(text)
        meta["has_tables"] = "|" in text and "---" in text
        meta["has_math"] = bool(re.search(r'\$\$|\$[^$]+\$', text))

        enhanced.append({"metadata": meta, "text": text})

    return enhanced


# ── 文件查找 ──────────────────────────────────────────────────
def find_pdfs(data_dir: str | Path) -> list[Path]:
    """递归查找 data/ 目录下所有 PDF 文件。"""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        logger.warning("data/ 目录不存在，正在创建...")
        data_dir.mkdir(parents=True, exist_ok=True)
        return []
    pdf_files = sorted(data_dir.rglob("*.pdf"))
    logger.info("找到 %d 个 PDF 文件", len(pdf_files))
    return pdf_files


def infer_book_name(pdf_path: Path, data_dir: Path) -> str:
    """从 PDF 路径推断书名。"""
    try:
        relative = pdf_path.relative_to(data_dir)
    except ValueError:
        return pdf_path.stem
    parts = relative.parts
    return parts[0] if len(parts) >= 2 else pdf_path.stem
