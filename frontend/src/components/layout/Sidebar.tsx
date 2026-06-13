import { NavLink } from 'react-router-dom'
import {
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/invoices', label: 'Invoices', icon: FileText },
  { to: '/reconciliation', label: 'Reconciliation', icon: GitCompareArrows },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-gradient-to-b from-primary-900 via-primary-900 to-primary-800 text-white shadow-[var(--shadow-elevated)]">
      <div className="border-b border-white/10 px-6 py-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/20">
            <Sparkles className="h-5 w-5 text-primary-100" />
          </div>
          <div>
            <p className="text-base font-semibold tracking-tight">FinFlow</p>
            <p className="text-xs text-indigo-200">Enterprise AP Platform</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-5">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? 'bg-white/15 text-white shadow-sm ring-1 ring-white/10'
                  : 'text-indigo-100 hover:bg-white/10 hover:text-white'
              }`
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 p-4">
        {user ? (
          <div className="mb-3 rounded-xl bg-white/5 px-3 py-2 ring-1 ring-white/10">
            <p className="truncate text-xs font-medium text-white">{user.email}</p>
            <p className="mt-0.5 text-[11px] capitalize text-indigo-200">
              {user.role.replace('_', ' ')}
            </p>
          </div>
        ) : null}
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-indigo-100 transition-colors hover:bg-white/10 hover:text-white"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
