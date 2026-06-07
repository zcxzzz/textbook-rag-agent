import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { User, Bot, ChevronDown, ChevronUp, FileText } from 'lucide-react'
import { ChatMessage as ChatMessageType, Theme } from '../types'

interface Props {
  message: ChatMessageType
  theme: Theme
}

export default function ChatMessage({ message, theme }: Props) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const isUser = message.role === 'user'
  const isDark = theme === 'dark'

  const assistantBg = isDark
    ? 'bg-neutral-900 border border-neutral-800 text-neutral-200'
    : 'bg-white border border-gray-200 text-gray-700'
  const assistRoleText = isDark ? 'text-neutral-500' : 'text-gray-400'
  const userAvatarBg = isDark ? 'bg-neutral-800' : 'bg-gray-200'
  const userAvatarIcon = isDark ? 'text-neutral-300' : 'text-gray-500'
  const sourceBorder = isDark ? 'border-neutral-800' : 'border-gray-200'
  const sourceBtnHover = isDark ? 'hover:text-neutral-300' : 'hover:text-gray-700'
  const sourceLinkText = isDark ? 'text-neutral-500' : 'text-gray-400'
  const sourceItemBg = isDark ? 'bg-neutral-950' : 'bg-gray-50'
  const sourceItemFileIcon = isDark ? 'text-neutral-600' : 'text-gray-400'
  const sourceItemFile = isDark ? 'text-neutral-300' : 'text-gray-700'
  const sourceItemPage = isDark ? 'text-neutral-600' : 'text-gray-400'
  const sourceItemHeading = isDark ? 'text-neutral-500' : 'text-gray-500'
  const sourceItemText = isDark ? 'text-neutral-400' : 'text-gray-500'
  const proseClass = isDark
    ? 'prose prose-invert prose-sm max-w-none prose-headings:text-white prose-p:leading-relaxed prose-strong:text-accent-hover prose-code:text-neutral-300 prose-ul:my-2 prose-li:my-0.5 [&_pre]:bg-neutral-950 [&_pre]:border [&_pre]:border-neutral-800 [&_pre]:rounded-lg [&_code]:text-xs'
    : 'prose prose-sm max-w-none prose-headings:text-gray-900 prose-p:leading-relaxed prose-strong:text-accent prose-code:text-gray-700 prose-ul:my-2 prose-li:my-0.5 [&_pre]:bg-gray-100 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:rounded-lg [&_code]:text-xs'

  return (
    <div className={`animate-slide-up ${isUser ? 'self-end max-w-[75%]' : 'self-start max-w-[85%]'}`}>
      {/* Avatar + role */}
      <div className={`flex items-center gap-2 mb-1 ${isUser ? 'justify-end' : ''}`}>
        {!isUser && (
          <div className="w-7 h-7 rounded-lg bg-accent/20 flex items-center justify-center">
            <Bot className="w-4 h-4 text-accent" />
          </div>
        )}
        <span className={`text-xs ${isDark ? 'text-neutral-500' : 'text-gray-400'}`}>
          {isUser ? '你' : '导师'}
        </span>
        {isUser && (
          <div className={`w-7 h-7 rounded-lg ${userAvatarBg} flex items-center justify-center`}>
            <User className={`w-4 h-4 ${userAvatarIcon}`} />
          </div>
        )}
      </div>

      {/* Bubble */}
      <div
        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-accent text-white rounded-br-md'
            : `${assistantBg} rounded-bl-md`
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className={proseClass}>
            <ReactMarkdown>{message.content || '▊'}</ReactMarkdown>
          </div>
        )}

        {/* Sources toggle (assistant only) */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className={`mt-2 pt-2 border-t ${sourceBorder}`}>
            <button
              onClick={() => setSourcesOpen(!sourcesOpen)}
              className={`flex items-center gap-1 text-xs ${sourceLinkText} ${sourceBtnHover} transition-colors`}
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
                    className={`text-xs ${sourceItemText} ${sourceItemBg} rounded-lg px-3 py-2 flex items-center gap-2`}
                  >
                    <FileText className={`w-3 h-3 flex-shrink-0 ${sourceItemFileIcon}`} />
                    <span className={`font-medium ${sourceItemFile}`}>{s.file}</span>
                    {s.page_label && (
                      <span className={sourceItemPage}>{s.page_label}</span>
                    )}
                    {s.heading && (
                      <span className={sourceItemHeading}>→ {s.heading}</span>
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
