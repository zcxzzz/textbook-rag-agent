import { useState, useEffect, useCallback, useRef } from 'react'
import { Sun, Moon } from 'lucide-react'
import LeftSidebar from './components/LeftSidebar'
import CenterPanel from './components/CenterPanel'
import RightPanel from './components/RightPanel'
import { api } from './api/client'
import { useChat } from './hooks/useChat'
import { Theme, ViewingPage, SourceChunk } from './types'

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme')
    return (saved === 'light' || saved === 'dark') ? saved : 'dark'
  })
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [bookName, setBookName] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0)
  const [viewingPage, setViewingPage] = useState<ViewingPage | null>(null)
  const sessionIdRef = useRef(sessionId)

  const {
    messages, knowledgeChunks, isStreaming, roundCount,
    sendMessage, stopStreaming, clearMessages, loadMessages,
  } = useChat()

  useEffect(() => {
    localStorage.setItem('theme', theme)
  }, [theme])

  // Keep ref in sync for beforeunload
  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  // ── Close current session (fire-and-forget, don't block switching) ──
  const closeCurrentSession = useCallback(() => {
    if (sessionIdRef.current) {
      api.closeSession(sessionIdRef.current).catch(() => {})
    }
  }, [])

  // ── Page-close: fire-and-forget via sendBeacon ──
  useEffect(() => {
    const onUnload = () => {
      const sid = sessionIdRef.current
      if (sid) api.closeSessionBeacon(sid)
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])

  // Initialise: auto-select first book and create session
  useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        const { books } = await api.getBooks()
        if (cancelled) return
        const defaultBook = books.length === 1 ? books[0] : null
        const session = await api.createSession(defaultBook)
        if (cancelled) return
        setBookName(defaultBook)
        setSessionId(session.session_id)
      } catch (e) {
        console.error('Init failed:', e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    init()
    return () => { cancelled = true }
  }, [])

  const handleBookChange = useCallback(async (name: string | null) => {
    closeCurrentSession()
    setBookName(name)
    try {
      const session = await api.createSession(name)
      setSessionId(session.session_id)
      clearMessages()
      setSessionRefreshKey(k => k + 1)
    } catch {}
  }, [clearMessages, closeCurrentSession])

  const handleNewSession = useCallback(async () => {
    closeCurrentSession()
    try {
      const session = await api.createSession(bookName)
      setSessionId(session.session_id)
      clearMessages()
      setSessionRefreshKey(k => k + 1)
    } catch {}
  }, [bookName, clearMessages, closeCurrentSession])

  const handleResumeSession = useCallback(async (id: string) => {
    closeCurrentSession()
    try {
      const info = await api.resumeSession(id)
      setSessionId(info.session_id)
      setBookName(info.book_name)
      const msgs = await api.getMessages(id)
      loadMessages(msgs)
    } catch {}
  }, [loadMessages, closeCurrentSession])

  const handleDeleteSession = useCallback(async (id: string) => {
    try {
      await api.deleteSession(id)
      if (id === sessionId) {
        // Deleted current session — create a new one
        const session = await api.createSession(bookName)
        setSessionId(session.session_id)
        clearMessages()
      }
      setSessionRefreshKey(k => k + 1)
    } catch {}
  }, [sessionId, bookName, clearMessages])

  const handleCommand = useCallback((cmd: string) => {
    if (!sessionId) return
    if (cmd === '/clear') {
      clearMessages()
      return
    }
    sendMessage(cmd, sessionId, bookName)
  }, [sessionId, bookName, sendMessage, clearMessages])

  const handleSend = useCallback((text: string) => {
    if (!sessionId) return
    sendMessage(text, sessionId, bookName)
  }, [sessionId, bookName, sendMessage])

  const handleViewSource = useCallback((chunk: SourceChunk) => {
    if (chunk.source_path) {
      setViewingPage({
        file: chunk.file,
        page: chunk.page,
        source_path: chunk.source_path,
        page_label: chunk.page_label,
      })
    }
  }, [])

  const handleClosePage = useCallback(() => {
    setViewingPage(null)
  }, [])

  const isDark = theme === 'dark'

  if (loading) {
    return (
      <div className={`h-screen flex items-center justify-center ${isDark ? 'bg-black' : 'bg-white'}`}>
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className={`text-sm ${isDark ? 'text-neutral-500' : 'text-gray-500'}`}>Loading models …</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`h-screen flex ${isDark ? 'bg-black text-white' : 'bg-white text-gray-900 light-scrollbar'}`}>
      <LeftSidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        bookName={bookName}
        onBookChange={handleBookChange}
        onNewSession={handleNewSession}
        onResumeSession={handleResumeSession}
        onDeleteSession={handleDeleteSession}
        onCommand={handleCommand}
        sessionId={sessionId}
        theme={theme}
        refreshKey={sessionRefreshKey}
      />
      <CenterPanel
        messages={messages}
        isStreaming={isStreaming}
        onSend={handleSend}
        onStop={stopStreaming}
        disabled={!sessionId}
        theme={theme}
      />
      <RightPanel
        chunks={knowledgeChunks}
        theme={theme}
        viewingPage={viewingPage}
        onViewSource={handleViewSource}
        onClosePage={handleClosePage}
      />
      {/* Theme toggle floating button */}
      <button
        onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
        className={`fixed bottom-6 right-6 w-10 h-10 rounded-xl flex items-center justify-center
          transition-colors z-50 shadow-lg
          ${isDark
            ? 'bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-white'
            : 'bg-white hover:bg-gray-100 text-gray-400 hover:text-gray-700 border border-gray-200'
          }`}
        title={isDark ? '切换浅色模式' : '切换深色模式'}
      >
        {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
    </div>
  )
}
