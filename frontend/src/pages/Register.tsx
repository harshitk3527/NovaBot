import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { useAuth } from '../auth/AuthContext'
import { errorMessage } from '../lib/utils'
import { Button, Input } from '../components/UI'
const schema = z.object({ email: z.string().email('Enter a valid email'), password: z.string().min(8, 'Password must be at least 8 characters') })
export default function Register() { const { register: signUp } = useAuth(); const navigate = useNavigate(); const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) }); const submit = async (data: z.infer<typeof schema>) => { try { await signUp(data.email, data.password); navigate('/chat') } catch (e) { toast.error(errorMessage(e)) } }; return <div className="grid min-h-[75vh] place-items-center"><div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900"><h1 className="text-2xl font-bold">Create your account</h1><p className="mb-7 mt-1 text-sm text-slate-500">Customer accounts are created automatically.</p><form onSubmit={handleSubmit(submit)} className="space-y-4"><label className="block text-sm font-medium">Email<Input type="email" {...register('email')} />{errors.email && <span className="text-xs text-red-600">{errors.email.message}</span>}</label><label className="block text-sm font-medium">Password<Input type="password" {...register('password')} />{errors.password && <span className="text-xs text-red-600">{errors.password.message}</span>}</label><Button disabled={isSubmitting} className="w-full">Create account</Button></form><p className="mt-5 text-center text-sm text-slate-500">Already registered? <Link to="/login" className="font-semibold text-blue-600">Sign in</Link></p></div></div> }
