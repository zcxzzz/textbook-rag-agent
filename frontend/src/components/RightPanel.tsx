import { useState, useEffect, useRef, useCallback } from 'react'
import { FileText, Link, ChevronLeft, ChevronRight, X, Loader, ZoomIn, ZoomOut, RotateCcw, GripVertical } from 'lucide-react'
import { SourceChunk, Theme, ViewingPage, PageInfo } from '../types'
import { api } from '../api/client'

interface Props {
  chunks: SourceChunk[]
  theme: Theme
  viewingPage: ViewingPage | null
  onViewSource: (chunk: SourceChunk) => void
  onClosePage: () => void
}

function SourceList({
  chunks, isDark, onViewSource,
}: {
  chunks: SourceChunk[]
  isDark: boolean
  onViewSource: (chunk: SourceChunk) => void
}) {
  const emptyIcon = isDark ? 'text-neutral-700' : 'text-gray-300'
  const emptyText = isDark ? 'text-neutral-600' : 'text-gray-400'

  if (!chunks.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <Link className={`w-8 h-8 ${emptyIcon} mb-3`} />
        <p className={`text-xs ${emptyText} leading-relaxed`}>
          知识来源将在这里显示。提问后，相关的教材段落会自动出现在这里。
          <br /><br />
          点击来源卡片可查看原 PDF 页面。
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-2">
      {chunks.map((chunk, i) => (
        <button
          key={i}
          onClick={() => onViewSource(chunk)}
          className={`w-full text-left rounded-xl border p-3 text-xs
            animate-fade-in transition-colors cursor-pointer
            ${isDark
              ? 'bg-neutral-900/80 border-neutral-800/60 hover:border-accent/40'
              : 'bg-white border-gray-200 hover:border-accent/40 shadow-sm'
            }`}
          style={{ animationDelay: `${i * 50}ms` }}
        >
          <div className={`flex items-center gap-1.5 ${isDark ? 'text-neutral-500' : 'text-gray-400'} mb-1.5`}>
            <FileText className="w-3 h-3 flex-shrink-0" />
            <span className={`font-medium truncate ${isDark ? 'text-neutral-300' : 'text-gray-700'}`}>
              {chunk.file}
            </span>
          </div>
          {chunk.page_label && (
            <span className="inline-block px-1.5 py-0.5 rounded bg-accent/10 text-accent-hover text-xs font-mono mb-1.5">
              {chunk.page_label}
            </span>
          )}
          {chunk.heading && (
            <p className={`${isDark ? 'text-neutral-400' : 'text-gray-500'} leading-relaxed mt-1`}>
              {chunk.heading}
            </p>
          )}
        </button>
      ))}
    </div>
  )
}

function PageViewer({
  viewingPage, isDark, onClosePage,
}: {
  viewingPage: ViewingPage
  isDark: boolean
  onClosePage: () => void
}) {
  const [currentPage, setCurrentPage] = useState(viewingPage.page)
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null)
  const [imgLoading, setImgLoading] = useState(true)
  const [zoom, setZoom] = useState(100)  // percent

  const ZOOM_MIN = 50
  const ZOOM_MAX = 300
  const ZOOM_STEP = 25

  // Higher backend scale for better quality when zoomed in
  const imageScale = zoom > 150 ? 3.0 : zoom > 100 ? 2.0 : 1.5

  const fetchInfo = async (p: number) => {
    try {
      const info = await api.getPageInfo(viewingPage.source_path, p)
      setPageInfo(info)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    fetchInfo(currentPage)
  }, [viewingPage.source_path, currentPage])

  const navigate = (delta: number) => {
    const next = currentPage + delta
    if (delta === 0 || (pageInfo && (next < 0 || next >= pageInfo.total))) return
    setImgLoading(true)
    setCurrentPage(next)
  }

  // Reset when source changes
  useEffect(() => {
    setCurrentPage(viewingPage.page)
    setImgLoading(true)
    setPageInfo(null)
  }, [viewingPage.source_path, viewingPage.page])

  const adjustZoom = (delta: number) => {
    setZoom(z => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z + delta)))
  }

  const containerBg = isDark ? 'bg-right-bg' : 'bg-gray-50'
  const borderColor = isDark ? 'border-sidebar-border' : 'border-gray-200'
  const titleText = isDark ? 'text-white' : 'text-gray-900'
  const metaText = isDark ? 'text-neutral-500' : 'text-gray-400'
  const btnEnabled = isDark
    ? 'hover:bg-neutral-800 text-neutral-400 hover:text-white'
    : 'hover:bg-gray-200 text-gray-400 hover:text-gray-700'
  const btnDisabled = isDark ? 'text-neutral-700' : 'text-gray-300'
  const navText = isDark ? 'text-neutral-500' : 'text-gray-400'
  const loadingText = isDark ? 'text-neutral-500' : 'text-gray-400'

  const displayLabel = pageInfo
    ? `p${currentPage + 1} / 共 ${pageInfo.total} 页`
    : (viewingPage.page_label || `p${currentPage + 1}`)

  const imageUrl = api.pageViewUrl(viewingPage.source_path, currentPage, imageScale)

  return (
    <div className={`flex-1 flex flex-col h-full ${containerBg}`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-3 py-2.5 border-b ${borderColor}`}>
        <div className="flex-1 min-w-0">
          <h3 className={`text-xs font-medium ${titleText} truncate`}>
            {viewingPage.file}
          </h3>
          <p className={`text-xs ${metaText} mt-0.5`}>{displayLabel}</p>
        </div>
        <button
          onClick={onClosePage}
          className={`p-1.5 rounded-lg ${btnEnabled} transition-colors flex-shrink-0 ml-2`}
          title="关闭"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Image viewer — zoomable; overflow-auto enables pan when scaled */}
      <div
        className={`flex-1 overflow-auto flex justify-center p-2 ${isDark ? 'bg-neutral-950' : 'bg-gray-100'}`}
      >
        {imgLoading && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
            <Loader className={`w-5 h-5 animate-spin ${loadingText}`} />
          </div>
        )}
        <div
          style={{
            transform: `scale(${zoom / 100})`,
            transformOrigin: 'top center',
            transition: 'transform 0.15s ease-out',
          }}
        >
          <img
            src={imageUrl}
            alt={`${viewingPage.file} ${displayLabel}`}
            onLoad={() => setImgLoading(false)}
            className="max-w-full h-auto rounded shadow-lg"
            style={{ imageRendering: 'auto' }}
          />
        </div>
      </div>

      {/* Footer: zoom row + navigation row */}
      <div className={`border-t ${borderColor}`}>
        {/* Zoom controls */}
        <div className={`flex items-center justify-center gap-1 px-3 py-2 border-b ${borderColor}`}>
          <button
            onClick={() => adjustZoom(-ZOOM_STEP)}
            disabled={zoom <= ZOOM_MIN}
            className={`p-1 rounded-md transition-colors ${zoom > ZOOM_MIN ? btnEnabled : `${btnDisabled} cursor-not-allowed`}`}
            title="缩小"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setZoom(100)}
            disabled={zoom === 100}
            className={`p-1 rounded-md transition-colors ${zoom !== 100 ? btnEnabled : `${btnDisabled} cursor-not-allowed`}`}
            title="还原"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <span className={`text-xs ${navText} min-w-[3rem] text-center tabular-nums select-none`}>
            {zoom}%
          </span>
          <button
            onClick={() => adjustZoom(+ZOOM_STEP)}
            disabled={zoom >= ZOOM_MAX}
            className={`p-1 rounded-md transition-colors ${zoom < ZOOM_MAX ? btnEnabled : `${btnDisabled} cursor-not-allowed`}`}
            title="放大"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Page navigation */}
        <div className="flex items-center justify-between px-3 py-2">
          <button
            onClick={() => navigate(-1)}
            disabled={!pageInfo || !pageInfo.has_prev}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors
              ${pageInfo?.has_prev ? btnEnabled : `${btnDisabled} cursor-not-allowed`}`}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            上一页
          </button>
          <span className={`text-xs ${navText} tabular-nums`}>
            {currentPage + 1}{pageInfo ? ` / ${pageInfo.total}` : ''}
          </span>
          <button
            onClick={() => navigate(1)}
            disabled={!pageInfo || !pageInfo.has_next}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors
              ${pageInfo?.has_next ? btnEnabled : `${btnDisabled} cursor-not-allowed`}`}
          >
            下一页
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function RightPanel({
  chunks, theme, viewingPage, onViewSource, onClosePage,
}: Props) {
  const isDark = theme === 'dark'
  const panelBg = isDark ? 'bg-right-bg' : 'bg-gray-50'
  const borderColor = isDark ? 'border-sidebar-border' : 'border-gray-200'
  const titleText = isDark ? 'text-white' : 'text-gray-900'
  const handleColor = isDark
    ? 'hover:bg-accent/50 bg-transparent'
    : 'hover:bg-accent/30 bg-transparent'

  const [panelWidth, setPanelWidth] = useState(320)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startW = useRef(0)

  const MIN_W = 240
  const MAX_W = 700

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    startX.current = e.clientX
    startW.current = panelWidth
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ew-resize'
  }, [panelWidth])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - e.clientX
      const next = Math.min(MAX_W, Math.max(MIN_W, startW.current + delta))
      setPanelWidth(next)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  return (
    <div
      style={{ width: panelWidth, minWidth: MIN_W, maxWidth: MAX_W }}
      className={`${panelBg} border-l ${borderColor} h-full flex flex-col flex-shrink-0 relative`}
    >
      {/* Resize handle — left edge */}
      <div
        onMouseDown={onMouseDown}
        className={`absolute -left-1 top-0 bottom-0 w-2 cursor-ew-resize
          flex items-center justify-center transition-colors z-10 ${handleColor}`}
        title="拖动调整宽度"
      >
        <GripVertical className="w-3 h-3 text-neutral-500 pointer-events-none" />
      </div>

      <div className={`px-4 py-3 border-b ${borderColor}`}>
        <h3 className={`text-sm font-medium ${titleText} flex items-center gap-2`}>
          <Link className="w-4 h-4 text-accent" />
          {viewingPage ? '教材原文' : '知识来源'}
        </h3>
      </div>

      {viewingPage ? (
        <PageViewer
          viewingPage={viewingPage}
          isDark={isDark}
          onClosePage={onClosePage}
        />
      ) : (
        <SourceList chunks={chunks} isDark={isDark} onViewSource={onViewSource} />
      )}
    </div>
  )
}
