import { useRef, useEffect } from 'react'
import { ChatMessage as ChatMessageType } from '../types'
import ChatMessageComponent from './ChatMessage'
import ChatInput from './ChatInput'
import WelcomeHero from './WelcomeHero'

interface Props {
  messages: ChatMessageType[]
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
  disabled?: boolean
}

export default function CenterPanel({
  messages, isStreaming, onSend, onStop, disabled,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  return (
    <div className="flex-1 flex flex-col h-full bg-center-bg">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeHero />
        ) : (
          <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
            {messages.map((msg) => (
              <ChatMessageComponent key={msg.id} message={msg} />
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
        />
      </div>
    </div>
  )
}
