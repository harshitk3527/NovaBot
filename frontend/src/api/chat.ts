import { api } from './client'
import type { ChatResponse } from './types'
export const sendMessage = (message: string, conversation_id?: string) => api.post<ChatResponse>('/chat', { message, ...(conversation_id ? { conversation_id } : {}) })
