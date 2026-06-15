import { useEffect, useState, type ReactNode } from 'react'
import { fetchMe } from '../api/auth'
import { useAuthStore } from '../store/authStore'

export function SessionBootstrap({ children }: { children: ReactNode }) {
  const setUser = useAuthStore((s) => s.setUser)
  const clearUser = useAuthStore((s) => s.clearUser)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true
    fetchMe()
      .then((user) => {
        if (active) setUser(user)
      })
      .catch(() => {
        if (active) clearUser()
      })
      .finally(() => {
        if (active) setReady(true)
      })
    return () => {
      active = false
    }
  }, [setUser, clearUser])

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-sm text-slate-400">
        Loading session…
      </div>
    )
  }

  return children
}
