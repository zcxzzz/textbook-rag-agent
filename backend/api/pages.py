"""GET /api/pages/view — render PDF page as PNG image via PyMuPDF."""
import logging
import os
import urllib.parse

import fitz
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger("backend.api.pages")

router = APIRouter()


@router.get("/pages/view")
async def view_page(
    source_path: str = Query(...),
    page: int = Query(...),
    scale: float = Query(1.5),
):
    """Render a single page of the source PDF as a PNG image.

    source_path = file system path to the PDF (URL-encoded)
    page        = 0-based page number (from chunk metadata)
    scale       = render scale factor (default 1.5x)
    """
    pdf_path = urllib.parse.unquote(source_path)
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=404, detail=f"PDF not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Cannot open PDF")

    if page < 0 or page >= len(doc):
        doc.close()
        raise HTTPException(status_code=404, detail=f"Page {page} out of range (total {len(doc)} pages)")

    try:
        pg = doc.load_page(page)
        mat = fitz.Matrix(scale, scale)
        pix = pg.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
    finally:
        doc.close()

    return Response(content=png_bytes, media_type="image/png")


@router.get("/pages/info")
async def page_info(source_path: str = Query(...), page: int = Query(...)):
    """Return page count for a PDF file (for prev/next navigation)."""
    pdf_path = urllib.parse.unquote(source_path)
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=404, detail=f"PDF not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        doc.close()
    except Exception:
        raise HTTPException(status_code=500, detail="Cannot open PDF")

    return {
        "page": page,
        "total": total,
        "has_prev": page > 0,
        "has_next": page < total - 1,
    }
