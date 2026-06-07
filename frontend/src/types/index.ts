export type Theme = 'dark' | 'light'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceChunk[]
}

export interface SourceChunk {
  file: string
  heading?: string | null
  book_name?: string | null
  source_path?: string | null
  page: number           // 0-based raw page number from Chroma metadata
  page_label?: string    // display label like "p42"
}

export interface PageInfo {
  page: number
  total: number
  has_prev: boolean
  has_next: boolean
}

export interface ViewingPage {
  file: string
  page: number           // 0-based
  source_path: string
  page_label?: string
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
