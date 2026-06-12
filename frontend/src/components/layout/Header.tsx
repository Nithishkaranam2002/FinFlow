import { Bell, Search } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

interface HeaderProps {
  title: string
  subtitle?: string
}

export function Header({ title, subtitle }: HeaderProps) {
  const user = useAuthStore((s) => s.user)

  return (
    <header className="flex items-center justify-between border-b border-border bg-surface px-8 py-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle ? <p className="mt-0.5 text-sm text-muted">{subtitle}</p> : null}
      </div>

      <div className="flex items-center gap-4">
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            placeholder="Search..."
            className="w-64 rounded-lg border border-border bg-canvas py-2 pl-9 pr-3 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
          />
        </div>
        <button
          type="button"
          className="rounded-lg border border-border p-2 text-muted transition-colors hover:bg-canvas hover:text-slate-900"
        >
          <Bell className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-3 rounded-lg border border-border bg-canvas px-3 py-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-700 text-xs font-semibold text-white">
            {user?.email?.[0]?.toUpperCase() ?? 'U'}
          </div>
          <div className="hidden sm:block">
            <p className="text-sm font-medium text-slate-900">{user?.email}</p>
            <p className="text-xs capitalize text-muted">{user?.role?.replace('_', ' ')}</p>
          </div>
        </div>
      </div>
    </header>
  )
}
