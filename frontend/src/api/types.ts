export type Role = 'admin' | 'customer'
export interface User { id: string; email: string; role: Role; tenant_id: string; is_active: boolean }
export interface Tokens { access_token: string; refresh_token: string; token_type?: string }
export interface ApiErrorShape { error?: { code?: string; message?: string } }
export class ApiError extends Error { status: number; code: string
  constructor(status: number, message: string, code = 'request_error') { super(message); this.status = status; this.code = code; this.name = 'ApiError' }
}
export interface Citation { document_id: string; title: string; version: string; page: number | null; chunk_id: string; snippet: string }
export interface ChatResponse { answer: string; citations: Citation[]; conversation_id: string; needs_human: boolean; cached: boolean }
export interface Conversation { id: string; created_at: string }
export interface Message { id: string; role: 'user' | 'assistant'; content: string; citations: Citation[] | null; created_at: string }
export type DocumentStatus = 'processing' | 'active' | 'superseded' | 'expired' | 'archived' | 'failed'
export interface Document { id: string; title: string; version: string; status: DocumentStatus; content_hash: string; valid_from: string; expires_at: string | null; uploaded_by: string; superseded_by: string | null; needs_review: boolean; created_at: string }
export interface DocumentList { items: Document[]; page: number; page_size: number; total: number }
