import { useState, useRef, useCallback } from 'react'
import { ChatMessage, SourceChunk } from '../types'
import { streamChat } from '../api/client'

let _msgId = 0
function nextId() {
  return `msg_${++_msgId}_${Date.now()}`
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [knowledgeChunks, setKnowledgeChunks] = useState<SourceChunk[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [roundCount, setRoundCount] = useState(0)
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    (text: string, sessionId: string, bookName: string | null) => {
      if (!sessionId || isStreaming) return

      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text,
      }
      const assistantId = nextId()
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      abortRef.current = streamChat(sessionId, bookName, text, {
        onToken: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + chunk }
                : m
            )
          )
        },
        onSources: (sources) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources } : m
            )
          )
          setKnowledgeChunks(sources)
        },
        onDone: (meta) => {
          setIsStreaming(false)
          setRoundCount(meta.round_count)
        },
        onError: (msg) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content || `Error: ${msg}` }
                : m
            )
          )
          setIsStreaming(false)
        },
      })
    },
    [isStreaming]
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setKnowledgeChunks([])
    setRoundCount(0)
  }, [])

  const loadMessages = useCallback(
    (msgs: { role: string; content: string }[]) => {
      const converted: ChatMessage[] = msgs.map((m) => ({
        id: nextId(),
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      setMessages(converted)
      setKnowledgeChunks([])
    },
    []
  )

  return {
    messages,
    knowledgeChunks,
    isStreaming,
    roundCount,
    sendMessage,
    stopStreaming,
    clearMessages,
    loadMessages,
  }
}
