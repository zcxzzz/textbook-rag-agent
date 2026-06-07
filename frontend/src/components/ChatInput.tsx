import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'
import { Theme } from '../types'

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
  theme: Theme
}

export default function ChatInput({ onSend, onStop, isStreaming, disabled, theme }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const isDark = theme === 'dark'

  useEffect(() => {
    if (!isStreaming && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isStreaming])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming || disabled) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-resize textarea
  useEffect(() => {
    const el = inputRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 160) + 'px'
    }
  }, [text])

  const containerClass = isDark
    ? 'bg-neutral-900 border-neutral-800 focus-within:border-accent/50'
    : 'bg-white border-gray-200 focus-within:border-accent/50 shadow-sm'
  const textClass = isDark ? 'text-white placeholder-neutral-600' : 'text-gray-900 placeholder-gray-400'

  return (
    <div className={`flex items-end gap-2 border rounded-2xl px-4 py-3 transition-colors ${containerClass}`}>
      <textarea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="向导师提问，或使用 / 命令…"
        rows={1}
        disabled={disabled}
        className={`flex-1 bg-transparent text-sm resize-none outline-none max-h-40 ${textClass}`}
      />
      {isStreaming ? (
        <button
          onClick={onStop}
          className="flex-shrink-0 w-9 h-9 rounded-xl bg-red-500/20 hover:bg-red-500/30
            flex items-center justify-center transition-colors"
        >
          <Square className="w-4 h-4 text-red-400" fill="currentColor" />
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={!text.trim() || disabled}
          className="flex-shrink-0 w-9 h-9 rounded-xl bg-accent hover:bg-accent-hover
            flex items-center justify-center transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4 text-white" />
        </button>
      )}
    </div>
  )
}
