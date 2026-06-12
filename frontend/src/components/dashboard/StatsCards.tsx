import {
  AlertCircle,
  DollarSign,
  FileStack,
  Percent,
} from 'lucide-react'
import type { DashboardStats } from '../../types'

interface StatsCardsProps {
  stats?: DashboardStats
  loading?: boolean
}

function sumStatusCounts(
  counts: DashboardStats['invoices_today'],
  statuses: string[],
) {
  return counts
    .filter((item) => statuses.includes(item.status))
    .reduce((sum, item) => sum + item.count, 0)
}

export function StatsCards({ stats, loading }: StatsCardsProps) {
  const cards = [
    {
      label: 'Invoices Today',
      value: stats
        ? stats.invoices_today.reduce((sum, item) => sum + item.count, 0).toString()
        : '—',
      icon: FileStack,
      tone: 'text-primary-700 bg-primary-50',
    },
    {
      label: 'Pending Approvals',
      value: stats
        ? sumStatusCounts(stats.invoices_today, ['pending_approval', 'review_required']).toString()
        : '—',
      icon: AlertCircle,
      tone: 'text-warning bg-amber-50',
    },
    {
      label: 'Exception Rate',
      value: stats ? `${stats.exception_rate.toFixed(1)}%` : '—',
      icon: Percent,
      tone: 'text-danger bg-red-50',
    },
    {
      label: 'Avg Cost / Invoice',
      value: stats ? `$${stats.cost_per_invoice_usd.toFixed(2)}` : '—',
      icon: DollarSign,
      tone: 'text-success bg-emerald-50',
    },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, icon: Icon, tone }) => (
        <div
          key={label}
          className="rounded-xl border border-border bg-surface p-5 shadow-sm"
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
              <p className="mt-3 text-3xl font-semibold text-slate-900">
                {loading ? '...' : value}
              </p>
            </div>
            <div className={`rounded-lg p-2.5 ${tone}`}>
              <Icon className="h-5 w-5" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
