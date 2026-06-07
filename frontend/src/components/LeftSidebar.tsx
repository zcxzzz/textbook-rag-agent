import { useState, useEffect, useMemo } from 'react'
import {
  BookOpen, Plus, PanelLeftClose, PanelLeft,
  BarChart3, Target, User, PenLine, Search, Trash2,
} from 'lucide-react'
import { api } from '../api/client'
import { SessionInfo, Theme } from '../types'

interface Props {
  collapsed: boolean
  onToggle: () => void
  bookName: string | null
  onBookChange: (name: string | null) => void
  onNewSession: () => void
  onResumeSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onCommand: (cmd: string) => void
  sessionId: string | null
  theme: Theme
  refreshKey: number
}

export default function LeftSidebar({
  collapsed, onToggle, bookName, onBookChange, onNewSession, onResumeSession,
  onDeleteSession, onCommand, sessionId, theme, refreshKey,
}: Props) {
  const [books, setBooks] = useState<string[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const isDark = theme === 'dark'

  useEffect(() => {
    api.getBooks().then((r) => setBooks(r.books)).catch(() => {})
  }, [])

  useEffect(() => {
    api.getSessionHistory(50).then(setSessions).catch(() => {})
  }, [sessionId, refreshKey])

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (window.confirm('确认删除这个会话？相关消息也会被删除。')) {
      onDeleteSession(id)
    }
  }

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

  const sidebarBg = isDark ? 'bg-sidebar-bg' : 'bg-gray-50'
  const sidebarBorder = isDark ? 'border-sidebar-border' : 'border-gray-200'
  const sidebarHover = isDark ? 'hover:bg-sidebar-hover' : 'hover:bg-gray-200'
  const textMuted = isDark ? 'text-neutral-500' : 'text-gray-500'
  const textDim = isDark ? 'text-neutral-600' : 'text-gray-400'
  const textNormal = isDark ? 'text-neutral-400' : 'text-gray-600'
  const textBright = isDark ? 'text-white' : 'text-gray-900'
  const activeBg = isDark ? 'bg-accent/10 text-accent-hover' : 'bg-accent/10 text-accent'
  const selectBg = isDark
    ? 'bg-sidebar-hover border-sidebar-border'
    : 'bg-white border-gray-300'
  const selectText = isDark ? 'text-white' : 'text-gray-900'
  const btnBase = isDark
    ? 'bg-sidebar-hover hover:bg-neutral-800 text-neutral-400 hover:text-white'
    : 'bg-gray-100 hover:bg-gray-200 text-gray-500 hover:text-gray-700'

  if (collapsed) {
    return (
      <div className={`w-14 flex flex-col items-center py-4 border-r ${sidebarBorder} ${sidebarBg}`}>
        <button
          onClick={onToggle}
          className={`p-2 rounded-lg ${sidebarHover} ${textMuted} hover:text-current transition-colors mb-4`}
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <div className="flex flex-col gap-2">
          <button
            onClick={onNewSession}
            className={`p-2 rounded-lg ${sidebarHover} ${textMuted} hover:text-current transition-colors`}
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
              className={`p-2 rounded-lg ${sidebarHover} ${textMuted} hover:text-current transition-colors`}
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
    <div className={`w-64 flex flex-col ${sidebarBg} border-r ${sidebarBorder} h-full`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-4 py-3 border-b ${sidebarBorder}`}>
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-accent" />
          <span className={`text-sm font-semibold ${textBright}`}>RAG Tutor</span>
        </div>
        <button
          onClick={onToggle}
          className={`p-1.5 rounded-lg ${sidebarHover} ${textMuted} hover:text-current transition-colors`}
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Book selector */}
      <div className={`px-4 py-3 border-b ${sidebarBorder}`}>
        <label className={`text-xs ${textMuted} mb-1.5 block`}>教材</label>
        <select
          value={bookName ?? '__all__'}
          onChange={(e) => {
            const v = e.target.value
            onBookChange(v === '__all__' ? null : v)
          }}
          className={`w-full border rounded-lg px-3 py-2 text-sm outline-none
            focus:border-accent/50 transition-colors appearance-none cursor-pointer
            ${selectBg} ${selectText}`}
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
              <p className={`text-xs ${textDim} px-1 mb-1.5`}>{label}</p>
              {list.map((s) => (
                <div key={s.session_id} className="group relative">
                  <button
                    onClick={() => onResumeSession(s.session_id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm truncate
                      transition-colors mb-0.5 pr-8
                      ${s.session_id === sessionId
                        ? activeBg
                        : `${textNormal} ${sidebarHover} hover:text-current`
                      }`}
                  >
                    <span className={`text-xs ${textDim} mr-2`}>
                      {s.session_id.slice(0, 6)}
                    </span>
                    {s.summary
                      ? s.summary.slice(0, 30) + (s.summary.length > 30 ? '…' : '')
                      : s.book_name || '未命名'}
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, s.session_id)}
                    className={`absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded
                      opacity-0 group-hover:opacity-100 transition-opacity
                      ${isDark
                        ? 'hover:bg-red-500/20 text-neutral-600 hover:text-red-400'
                        : 'hover:bg-red-50 text-gray-400 hover:text-red-500'
                      }`}
                    title="删除会话"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* Quick commands */}
      <div className={`px-4 py-3 border-t ${sidebarBorder}`}>
        <p className={`text-xs ${textDim} mb-2`}>快捷命令</p>
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
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg
                text-xs transition-colors ${btnBase}`}
            >
              <Icon className="w-3 h-3" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Session ID display */}
      {sessionId && (
        <div className={`px-4 py-2 border-t ${sidebarBorder}`}>
          <p className={`text-xs ${textDim} truncate`}>
            {sessionId}
          </p>
        </div>
      )}
    </div>
  )
}
