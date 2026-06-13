import { ShieldCheck } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

interface HeaderProps {
  title: string
  subtitle?: string
}

export function Header({ title, subtitle }: HeaderProps) {
  const user = useAuthStore((s) => s.user)

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/95 px-8 py-5 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 md:flex">
            <ShieldCheck className="h-3.5 w-3.5" />
            SOC-ready audit trail
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-canvas px-3 py-2 shadow-sm">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-700 text-sm font-semibold text-white">
              {user?.email?.[0]?.toUpperCase() ?? 'U'}
            </div>
            <div className="hidden sm:block">
              <p className="max-w-[180px] truncate text-sm font-medium text-slate-900">
                {user?.email}
              </p>
              <p className="text-xs capitalize text-muted">{user?.role?.replace('_', ' ')}</p>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
