import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
}

export default function ChatInput({ onSend, onStop, isStreaming, disabled }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

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

  return (
    <div className="flex items-end gap-2 bg-neutral-900 border border-neutral-800 rounded-2xl px-4 py-3 focus-within:border-accent/50 transition-colors">
      <textarea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="向导师提问，或使用 / 命令…"
        rows={1}
        disabled={disabled}
        className="flex-1 bg-transparent text-sm text-white placeholder-neutral-600
          resize-none outline-none max-h-40"
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
