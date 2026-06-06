import { useState, useEffect, useMemo } from 'react'
import {
  BookOpen, Plus, PanelLeftClose, PanelLeft, Zap,
  BarChart3, Target, User, PenLine, Search,
} from 'lucide-react'
import { api } from '../api/client'
import { SessionInfo } from '../types'

interface Props {
  collapsed: boolean
  onToggle: () => void
  bookName: string | null
  onBookChange: (name: string | null) => void
  onNewSession: () => void
  onResumeSession: (id: string) => void
  onCommand: (cmd: string) => void
  sessionId: string | null
}

export default function LeftSidebar({
  collapsed, onToggle, bookName, onBookChange, onNewSession, onResumeSession,
  onCommand, sessionId,
}: Props) {
  const [books, setBooks] = useState<string[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])

  useEffect(() => {
    api.getBooks().then((r) => setBooks(r.books)).catch(() => {})
  }, [])

  useEffect(() => {
    api.getSessionHistory(50).then(setSessions).catch(() => {})
  }, [sessionId])

  // Group sessions by time
  const groupedSessions = useMemo(() => {
    const now = Date.now()
    const today: SessionInfo[] = []
    const week: SessionInfo[] = []
    const older: SessionInfo[] = []

    for (const s of sessions) {
      const ts = new Date(s.created_at).getTime()
      const diff = now - ts
      if (diff < 24 * 3600_000) today.push(s)
      else if (diff < 7 * 24 * 3600_000) week.push(s)
      else older.push(s)
    }
    return { today, week, older }
  }, [sessions])

  if (collapsed) {
    return (
      <div className="w-14 flex flex-col items-center py-4 border-r border-sidebar-border bg-sidebar-bg">
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-sidebar-hover text-neutral-500 hover:text-white transition-colors mb-4"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <div className="flex flex-col gap-2">
          <button
            onClick={onNewSession}
            className="p-2 rounded-lg hover:bg-sidebar-hover text-neutral-500 hover:text-white transition-colors"
            title="新对话"
          >
            <Plus className="w-5 h-5" />
          </button>
          {[
            { cmd: '/progress', icon: BarChart3, label: '学习进度' },
            { cmd: '/quiz 3', icon: PenLine, label: '出题' },
            { cmd: '/weakpoints', icon: Target, label: '薄弱点' },
          ].map(({ cmd, icon: Icon, label }) => (
            <button
              key={cmd}
              onClick={() => onCommand(cmd)}
              className="p-2 rounded-lg hover:bg-sidebar-hover text-neutral-500 hover:text-white transition-colors"
              title={label}
            >
              <Icon className="w-5 h-5" />
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="w-64 flex flex-col bg-sidebar-bg border-r border-sidebar-border h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-sidebar-border">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-accent" />
          <span className="text-sm font-semibold text-white">RAG Tutor</span>
        </div>
        <button
          onClick={onToggle}
          className="p-1.5 rounded-lg hover:bg-sidebar-hover text-neutral-500 hover:text-white transition-colors"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Book selector */}
      <div className="px-4 py-3 border-b border-sidebar-border">
        <label className="text-xs text-neutral-500 mb-1.5 block">教材</label>
        <select
          value={bookName ?? '__all__'}
          onChange={(e) => {
            const v = e.target.value
            onBookChange(v === '__all__' ? null : v)
          }}
          className="w-full bg-sidebar-hover border border-sidebar-border rounded-lg px-3 py-2
            text-sm text-white outline-none focus:border-accent/50 transition-colors
            appearance-none cursor-pointer"
        >
          <option value="__all__">全部教材</option>
          {books.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
      </div>

      {/* New session button */}
      <div className="px-4 py-3">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-xl
            bg-accent/10 hover:bg-accent/20 text-accent-hover text-sm
            transition-colors"
        >
          <Plus className="w-4 h-4" />
          新对话
        </button>
      </div>

      {/* Session history */}
      <div className="flex-1 overflow-y-auto px-3 space-y-4">
        {(['today', 'week', 'older'] as const).map((group) => {
          const list = groupedSessions[group]
          if (!list.length) return null
          const label = group === 'today' ? '今天' : group === 'week' ? '7 天内' : '更早'
          return (
            <div key={group}>
              <p className="text-xs text-neutral-600 px-1 mb-1.5">{label}</p>
              {list.map((s) => (
                <button
                  key={s.session_id}
                  onClick={() => onResumeSession(s.session_id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm truncate
                    transition-colors mb-0.5
                    ${s.session_id === sessionId
                      ? 'bg-accent/10 text-accent-hover'
                      : 'text-neutral-400 hover:bg-sidebar-hover hover:text-white'
                    }`}
                >
                  <span className="text-xs text-neutral-600 mr-2">
                    {s.session_id.slice(0, 6)}
                  </span>
                  {s.summary
                    ? s.summary.slice(0, 30) + (s.summary.length > 30 ? '…' : '')
                    : s.book_name || '未命名'}
                </button>
              ))}
            </div>
          )
        })}
      </div>

      {/* Quick commands */}
      <div className="px-4 py-3 border-t border-sidebar-border">
        <p className="text-xs text-neutral-600 mb-2">快捷命令</p>
        <div className="flex flex-wrap gap-1.5">
          {[
            { cmd: '/progress', icon: BarChart3, label: '进度' },
            { cmd: '/weakpoints', icon: Target, label: '薄弱点' },
            { cmd: '/quiz 3', icon: PenLine, label: '出题×3' },
            { cmd: '/quiz 5', icon: PenLine, label: '出题×5' },
            { cmd: '/profile', icon: User, label: '画像' },
            { cmd: '/explain', icon: Search, label: '讲解' },
          ].map(({ cmd, icon: Icon, label }) => (
            <button
              key={cmd}
              onClick={() => onCommand(cmd)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg
                bg-sidebar-hover hover:bg-neutral-800 text-xs text-neutral-400
                hover:text-white transition-colors"
            >
              <Icon className="w-3 h-3" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Session ID display */}
      {sessionId && (
        <div className="px-4 py-2 border-t border-sidebar-border">
          <p className="text-xs text-neutral-600 truncate">
            {sessionId}
          </p>
        </div>
      )}
    </div>
  )
}
