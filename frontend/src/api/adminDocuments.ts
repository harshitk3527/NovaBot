import { api } from './client'
import type { Document, DocumentList } from './types'
export const listDocuments = (params: { status?: string; page: number; page_size: number }) => api.get<DocumentList>('/admin/documents', { params })
export const getDocument = (id: string) => api.get<Document>(`/admin/documents/${id}`)
export const currentVersion = () => api.get<{ kb_version: number }>('/admin/documents/version/current')
export const updateDocument = (id: string, data: { status?: 'archive' | 'approve'; expires_at?: string | null }) => api.patch<Document>(`/admin/documents/${id}`, data)
export const removeDocument = (id: string) => api.delete(`/admin/documents/${id}`)
export const uploadDocument = (form: FormData, onUploadProgress?: (event: ProgressEvent) => void) => api.post<Document>('/admin/documents', form, { headers: { 'Content-Type': 'multipart/form-data' }, onUploadProgress })
export const replaceDocument = (id: string, form: FormData, onUploadProgress?: (event: ProgressEvent) => void) => api.put<Document>(`/admin/documents/${id}`, form, { headers: { 'Content-Type': 'multipart/form-data' }, onUploadProgress })
