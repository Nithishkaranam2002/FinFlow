import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, LockKeyhole } from 'lucide-react'
import { isAxiosError } from 'axios'
import { fetchMe, login } from '../api/invoices'
import { useAuthStore } from '../store/authStore'

export function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const tokenResponse = await login(email.trim(), password)
      const user = await fetchMe(tokenResponse.access_token)
      setAuth(tokenResponse.access_token, user)
      navigate('/')
    } catch (err) {
      if (isAxiosError(err)) {
        const status = err.response?.status
        const detail = err.response?.data?.detail
        if (status === 401) {
          setError('Invalid email or password. Please try again.')
        } else if (typeof detail === 'string') {
          setError(detail)
        } else {
          setError('Unable to sign in. Check that the API is running on port 8000.')
        }
      } else {
        setError('Unable to sign in. Check that the API is running on port 8000.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary-900 via-primary-800 to-slate-900 px-4">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white p-8 shadow-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary-900 text-sm font-bold text-white">
            FF
          </div>
          <h1 className="mt-4 text-2xl font-semibold text-slate-900">Welcome to FinFlow</h1>
          <p className="mt-2 text-sm text-muted">Sign in to your enterprise finance workspace</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2.5 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
              placeholder="you@company.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2.5 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
              placeholder="••••••••"
            />
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-800 disabled:opacity-60"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}
            Sign in
          </button>
        </form>

        {import.meta.env.DEV ? (
          <div className="mt-6 rounded-lg border border-dashed border-border bg-slate-50 p-4 text-xs text-muted">
            <p className="font-medium text-slate-700">Local dev credentials</p>
            <p className="mt-1">
              <span className="font-mono text-slate-800">controller@acmecorp.com</span>
              {' / '}
              <span className="font-mono text-slate-800">Test1234!</span>
            </p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
