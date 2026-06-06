export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceChunk[]
}

export interface SourceChunk {
  file: string
  page?: string | null
  heading?: string | null
}

export interface SessionInfo {
  session_id: string
  book_name: string | null
  created_at: string
  closed_at: string | null
  total_messages: number
  summary: string | null
}

export interface Stats {
  total_sessions: number
  total_topics_learned: number
  active_weak_points: number
}
