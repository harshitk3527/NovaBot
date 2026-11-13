import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProtectedRoute from './ProtectedRoute'
import AdminRoute from './AdminRoute'
vi.mock('./AuthContext', () => ({ useAuth: vi.fn() }))
import { useAuth } from './AuthContext'
const mockedAuth = vi.mocked(useAuth)
describe('route guards', () => {
  it('redirects an unauthenticated user', () => { mockedAuth.mockReturnValue({ user: null, booting: false, login: vi.fn(), register: vi.fn(), logout: vi.fn() }); render(<MemoryRouter initialEntries={['/private']}><Routes><Route element={<ProtectedRoute />}><Route path="/private" element={<p>private</p>} /></Route><Route path="/login" element={<p>login</p>} /></Routes></MemoryRouter>); expect(screen.getByText('login')).toBeInTheDocument() })
  it('redirects a customer from admin routes', () => { mockedAuth.mockReturnValue({ user: { id: '1', email: 'a', role: 'customer', tenant_id: 't', is_active: true }, booting: false, login: vi.fn(), register: vi.fn(), logout: vi.fn() }); render(<MemoryRouter initialEntries={['/admin']}><Routes><Route element={<AdminRoute />}><Route path="/admin" element={<p>admin</p>} /></Route><Route path="/chat" element={<p>chat</p>} /></Routes></MemoryRouter>); expect(screen.getByText('chat')).toBeInTheDocument() })
})
