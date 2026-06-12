import type { InvoiceStatus } from '../types'
import { STATUS_STYLES } from './invoiceUtils'

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[status]}`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function RiskScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score * 100))
  const color =
    score >= 0.7 ? 'bg-red-500' : score >= 0.4 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted">{score.toFixed(2)}</span>
    </div>
  )
}

export function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence == null) return <span className="text-xs text-muted">—</span>
  const pct = Math.round(confidence * 100)
  const color =
    confidence >= 0.85
      ? 'bg-emerald-50 text-emerald-700'
      : confidence >= 0.75
        ? 'bg-slate-100 text-slate-700'
        : 'bg-amber-50 text-amber-800'

  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium tabular-nums ${color}`}>
      {pct}%
    </span>
  )
}

export function formatCurrency(amount: string | number, currency = 'USD') {
  const value = typeof amount === 'string' ? parseFloat(amount) : amount
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(value || 0)
}

export function formatDate(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
