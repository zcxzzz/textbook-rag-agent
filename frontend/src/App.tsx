import { useState, useEffect, useCallback } from 'react'
import LeftSidebar from './components/LeftSidebar'
import CenterPanel from './components/CenterPanel'
import RightPanel from './components/RightPanel'
import { api } from './api/client'
import { useChat } from './hooks/useChat'

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [bookName, setBookName] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const {
    messages, knowledgeChunks, isStreaming, roundCount,
    sendMessage, stopStreaming, clearMessages, loadMessages,
  } = useChat()

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
    setBookName(name)
    try {
      const session = await api.createSession(name)
      setSessionId(session.session_id)
      clearMessages()
    } catch {}
  }, [clearMessages])

  const handleNewSession = useCallback(async () => {
    try {
      const session = await api.createSession(bookName)
      setSessionId(session.session_id)
      clearMessages()
    } catch {}
  }, [bookName, clearMessages])

  const handleResumeSession = useCallback(async (id: string) => {
    try {
      const info = await api.resumeSession(id)
      setSessionId(info.session_id)
      setBookName(info.book_name)
      const msgs = await api.getMessages(id)
      loadMessages(msgs)
    } catch {}
  }, [loadMessages])

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

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-neutral-500 text-sm">Loading models …</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen flex bg-black text-white">
      <LeftSidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        bookName={bookName}
        onBookChange={handleBookChange}
        onNewSession={handleNewSession}
        onResumeSession={handleResumeSession}
        onCommand={handleCommand}
        sessionId={sessionId}
      />
      <CenterPanel
        messages={messages}
        isStreaming={isStreaming}
        onSend={handleSend}
        onStop={stopStreaming}
        disabled={!sessionId}
      />
      <RightPanel chunks={knowledgeChunks} />
    </div>
  )
}
