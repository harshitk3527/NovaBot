import { Link, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { useAuth } from '../auth/AuthContext'
import { errorMessage } from '../lib/utils'
import { Button, Input } from '../components/UI'
const schema = z.object({ email: z.string().email('Enter a valid email'), password: z.string().min(8, 'Password must be at least 8 characters') })
type Form = z.infer<typeof schema>
export default function Login() { const { login } = useAuth(); const navigate = useNavigate(); const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema) }); const submit = async (data: Form) => { try { await login(data.email, data.password); navigate('/chat') } catch (e) { toast.error(errorMessage(e)) } }; return <AuthCard title="Welcome back" subtitle="Sign in to your support workspace"><form onSubmit={handleSubmit(submit)} className="space-y-4">{(['email', 'password'] as const).map(field => <label key={field} className="block text-sm font-medium">{field === 'email' ? 'Email' : 'Password'}<Input type={field === 'email' ? 'email' : 'password'} {...register(field)} />{errors[field] && <span className="text-xs text-red-600">{errors[field]?.message}</span>}</label>)}<Button disabled={isSubmitting} className="w-full">{isSubmitting ? 'Signing in…' : 'Sign in'}</Button></form><p className="mt-5 text-center text-sm text-slate-500">Need an account? <Link to="/register" className="font-semibold text-blue-600">Create one</Link></p></AuthCard> }
function AuthCard({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <div className="grid min-h-[75vh] place-items-center"><div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900"><h1 className="text-2xl font-bold">{title}</h1><p className="mb-7 mt-1 text-sm text-slate-500">{subtitle}</p>{children}</div></div> }
