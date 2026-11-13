import { Link } from 'react-router-dom'
export default function NotFound() { return <div className="grid min-h-screen place-items-center text-center"><div><p className="text-6xl font-bold text-blue-600">404</p><h1 className="mt-3 text-2xl font-bold">Page not found</h1><Link to="/chat" className="mt-5 inline-block text-blue-600">Return to chat</Link></div></div> }
