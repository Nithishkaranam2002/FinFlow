import type { FraudFlag } from '../../types'

const severityCardStyles: Record<FraudFlag['severity'], string> = {
  LOW: 'border-slate-200 bg-slate-50',
  MEDIUM: 'border-yellow-200 bg-yellow-50',
  HIGH: 'border-amber-300 bg-amber-50',
  CRITICAL: 'border-red-300 bg-red-50',
}

const severityTextStyles: Record<FraudFlag['severity'], string> = {
  LOW: 'text-slate-700',
  MEDIUM: 'text-yellow-900',
  HIGH: 'text-amber-900',
  CRITICAL: 'text-red-900',
}

const severityBadgeStyles: Record<FraudFlag['severity'], string> = {
  LOW: 'border-slate-200 bg-slate-50 text-slate-700',
  MEDIUM: 'border-yellow-200 bg-yellow-50 text-yellow-800',
  HIGH: 'border-amber-200 bg-amber-50 text-amber-800',
  CRITICAL: 'border-red-200 bg-red-50 text-red-800',
}

export function FraudFlagBadge({ flag }: { flag: FraudFlag }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${severityBadgeStyles[flag.severity]}`}
    >
      <span className="font-semibold">{flag.severity}</span>
      <span className="opacity-70">·</span>
      <span>{flag.type.replace(/_/g, ' ')}</span>
    </span>
  )
}

export function FraudFlagCard({ flag }: { flag: FraudFlag }) {
  return (
    <article className={`rounded-xl border p-4 ${severityCardStyles[flag.severity]}`}>
      <div className="flex items-center justify-between gap-3">
        <p className={`text-xs font-bold uppercase tracking-wide ${severityTextStyles[flag.severity]}`}>
          {flag.severity}
        </p>
        <p className="text-xs font-medium text-muted">{flag.type.replace(/_/g, ' ')}</p>
      </div>
      <p className={`mt-2 text-sm ${severityTextStyles[flag.severity]}`}>{flag.description}</p>
    </article>
  )
}

export function FraudFlagList({ flags }: { flags: FraudFlag[] }) {
  if (!flags.length) {
    return <p className="text-sm text-muted">No fraud flags detected.</p>
  }

  return (
    <div className="flex flex-wrap gap-2">
      {flags.map((flag, index) => (
        <FraudFlagBadge key={`${flag.type}-${index}`} flag={flag} />
      ))}
    </div>
  )
}
