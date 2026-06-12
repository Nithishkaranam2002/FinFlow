import { NavLink } from 'react-router-dom'
import {
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  LogOut,
  Settings,
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

  return (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-primary-900 text-white">
      <div className="border-b border-white/10 px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-sm font-bold">
            FF
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide">FinFlow</p>
            <p className="text-xs text-blue-200">Invoice Intelligence</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-white/15 text-white shadow-sm'
                  : 'text-blue-100 hover:bg-white/10 hover:text-white'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 p-3">
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-blue-100 transition-colors hover:bg-white/10 hover:text-white"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
