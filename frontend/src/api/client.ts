const BASE = '/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

export const api = {
  getBooks: () => request<{ books: string[] }>('/books'),

  createSession: (bookName: string | null) =>
    request<import('../types').SessionInfo>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ book_name: bookName }),
    }),

  resumeSession: (sessionId: string) =>
    request<import('../types').SessionInfo>(`/sessions/${sessionId}/resume`, {
      method: 'POST',
    }),

  getMessages: (sessionId: string) =>
    request<{ role: string; content: string }[]>(
      `/sessions/${sessionId}/messages`
    ),

  getSessionHistory: (limit = 20) =>
    request<import('../types').SessionInfo[]>(`/sessions/history?limit=${limit}`),

  getStats: (bookName?: string | null) =>
    request<import('../types').Stats>(
      `/stats${bookName ? `?book_name=${encodeURIComponent(bookName)}` : ''}`
    ),
}

/**
 * SSE streaming chat.
 * Calls onToken / onSources / onDone / onError callbacks as events arrive.
 */
export function streamChat(
  sessionId: string,
  bookName: string | null,
  message: string,
  callbacks: {
    onToken: (text: string) => void
    onSources: (sources: import('../types').SourceChunk[]) => void
    onDone: (meta: { round_count: number; compressed: boolean }) => void
    onError: (msg: string) => void
  }
): AbortController {
  const controller = new AbortController()

  const params = new URLSearchParams({ session_id: sessionId })
  if (bookName) params.set('book_name', bookName)

  fetch(`${BASE}/chat/stream?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        callbacks.onError(`HTTP ${res.status}`)
        return
      }
      const reader = res.body?.getReader()
      if (!reader) return

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Parse SSE frames
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6)
            try {
              const parsed = JSON.parse(data)
              switch (eventType) {
                case 'token':
                  callbacks.onToken(parsed.content)
                  break
                case 'sources':
                  callbacks.onSources(parsed.sources)
                  break
                case 'done':
                  callbacks.onDone(parsed)
                  break
                case 'error':
                  callbacks.onError(parsed.message)
                  break
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError(err.message)
      }
    })

  return controller
}
