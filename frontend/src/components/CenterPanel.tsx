import { useRef, useEffect } from 'react'
import { ChatMessage as ChatMessageType, Theme } from '../types'
import ChatMessageComponent from './ChatMessage'
import ChatInput from './ChatInput'
import WelcomeHero from './WelcomeHero'

interface Props {
  messages: ChatMessageType[]
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
  disabled?: boolean
  theme: Theme
}

export default function CenterPanel({
  messages, isStreaming, onSend, onStop, disabled, theme,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const isDark = theme === 'dark'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  return (
    <div className={`flex-1 flex flex-col h-full ${isDark ? 'bg-center-bg' : 'bg-gray-100'}`}>
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeHero theme={theme} />
        ) : (
          <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
            {messages.map((msg) => (
              <ChatMessageComponent key={msg.id} message={msg} theme={theme} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="max-w-3xl mx-auto w-full px-6 pb-6">
        <ChatInput
          onSend={onSend}
          onStop={onStop}
          isStreaming={isStreaming}
          disabled={disabled}
          theme={theme}
        />
      </div>
    </div>
  )
}
