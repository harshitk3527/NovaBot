import { api } from './client'
import type { Conversation, Message } from './types'
export const listConversations = () => api.get<Conversation[]>('/conversations')
export const getMessages = (id: string) => api.get<Message[]>(`/conversations/${id}/messages`)
export const deleteConversation = (id: string) => api.delete(`/conversations/${id}`)
