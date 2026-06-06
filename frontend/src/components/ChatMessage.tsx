import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { User, Bot, ChevronDown, ChevronUp, FileText } from 'lucide-react'
import { ChatMessage as ChatMessageType } from '../types'

interface Props {
  message: ChatMessageType
}

export default function ChatMessage({ message }: Props) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={`animate-slide-up ${isUser ? 'self-end max-w-[75%]' : 'self-start max-w-[85%]'}`}>
      {/* Avatar + role */}
      <div className={`flex items-center gap-2 mb-1 ${isUser ? 'justify-end' : ''}`}>
        {!isUser && (
          <div className="w-7 h-7 rounded-lg bg-accent/20 flex items-center justify-center">
            <Bot className="w-4 h-4 text-accent" />
          </div>
        )}
        <span className="text-xs text-neutral-500">{isUser ? '你' : '导师'}</span>
        {isUser && (
          <div className="w-7 h-7 rounded-lg bg-neutral-800 flex items-center justify-center">
            <User className="w-4 h-4 text-neutral-300" />
          </div>
        )}
      </div>

      {/* Bubble */}
      <div
        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-accent text-white rounded-br-md'
            : 'bg-neutral-900 border border-neutral-800 text-neutral-200 rounded-bl-md'
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none
            prose-headings:text-white prose-p:leading-relaxed
            prose-strong:text-accent-hover prose-code:text-neutral-300
            prose-ul:my-2 prose-li:my-0.5
            [&_pre]:bg-neutral-950 [&_pre]:border [&_pre]:border-neutral-800 [&_pre]:rounded-lg
            [&_code]:text-xs">
            <ReactMarkdown>{message.content || '▊'}</ReactMarkdown>
          </div>
        )}

        {/* Sources toggle (assistant only) */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-neutral-800">
            <button
              onClick={() => setSourcesOpen(!sourcesOpen)}
              className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              <FileText className="w-3 h-3" />
              参考来源 ({message.sources.length})
              {sourcesOpen ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </button>
            {sourcesOpen && (
              <div className="mt-2 space-y-1.5">
                {message.sources.map((s, i) => (
                  <div
                    key={i}
                    className="text-xs text-neutral-400 bg-neutral-950 rounded-lg px-3 py-2 flex items-center gap-2"
                  >
                    <FileText className="w-3 h-3 flex-shrink-0 text-neutral-600" />
                    <span className="font-medium text-neutral-300">{s.file}</span>
                    {s.page && (
                      <span className="text-neutral-600">{s.page}</span>
                    )}
                    {s.heading && (
                      <span className="text-neutral-500">→ {s.heading}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
