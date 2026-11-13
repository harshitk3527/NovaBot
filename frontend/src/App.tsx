import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { useAuth } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import AdminRoute from './auth/AdminRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Chat from './pages/Chat'
import AdminDocuments from './pages/AdminDocuments'
import NotFound from './pages/NotFound'
import AppShell from './components/AppShell'

export default function App() {
  const { user, booting } = useAuth()
  if (booting) return <div className="min-h-screen grid place-items-center"><div className="spinner" aria-label="Loading" /></div>
  return <>
    <Toaster position="top-right" richColors />
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/chat" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/chat" replace /> : <Register />} />
      <Route element={<ProtectedRoute />}><Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<Chat />} />
        <Route element={<AdminRoute />}><Route path="/admin/documents" element={<AdminDocuments />} /></Route>
      </Route></Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  </>
}
