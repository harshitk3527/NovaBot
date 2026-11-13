import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'
export default function AdminRoute() { return useAuth().user?.role === 'admin' ? <Outlet /> : <Navigate to="/chat" replace /> }
