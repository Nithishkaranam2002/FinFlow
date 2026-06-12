import type { DashboardStats } from '../../types'
import { formatDate } from '../../lib/utils'

interface ProcessingTimelineProps {
  stats?: DashboardStats
  loading?: boolean
}

export function ProcessingTimeline({ stats, loading }: ProcessingTimelineProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
        Loading processing metrics...
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-900">Processing Overview</h3>
      <p className="mt-1 text-xs text-muted">Operational throughput this month</p>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-lg bg-canvas p-4">
          <p className="text-xs uppercase tracking-wide text-muted">Avg Processing Time</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">
            {stats?.average_processing_time_hours.toFixed(1) ?? '0.0'}h
          </p>
        </div>
        <div className="rounded-lg bg-canvas p-4">
          <p className="text-xs uppercase tracking-wide text-muted">Invoices This Month</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">
            {stats?.invoices_this_month.reduce((sum, item) => sum + item.count, 0) ?? 0}
          </p>
        </div>
        <div className="rounded-lg bg-canvas p-4">
          <p className="text-xs uppercase tracking-wide text-muted">Last Updated</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{formatDate(new Date().toISOString())}</p>
        </div>
      </div>
    </div>
  )
}
