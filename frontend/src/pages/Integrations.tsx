import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RotateCw, Shield, Webhook } from 'lucide-react'
import {
  getWebhookSummary,
  listWebhookDeliveries,
  retryWebhookDelivery,
} from '../api/integrations'
import { getApiErrorMessage } from '../api/client'
import { hasMinRole } from '../lib/invoiceUtils'
import { notifyError, notifySuccess } from '../lib/toast'
import { useAuthStore } from '../store/authStore'
import type { WebhookDeliveryStatus, WebhookSummary } from '../types'

const REFRESH_MS = 5000

const DELIVERY_STATUS: Record<WebhookDeliveryStatus, { label: string; className: string }> = {
  sent: { label: 'Sent', className: 'bg-emerald-100 text-emerald-800' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
  pending: { label: 'Sending', className: 'bg-amber-100 text-amber-800' },
}

function formatTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  })
}

function connectionHealth(summary: WebhookSummary | undefined) {
  if (!summary?.configured) {
    return { dot: 'bg-slate-400', text: 'Not configured', tone: 'text-muted' }
  }
  if (summary.last_status === 'failed') {
    return { dot: 'bg-red-500', text: 'Last delivery failed', tone: 'text-red-700' }
  }
  if (summary.last_status === 'sent') {
    return { dot: 'bg-emerald-500', text: 'Healthy', tone: 'text-emerald-700' }
  }
  if (summary.last_status === 'pending') {
    return { dot: 'bg-amber-500', text: 'Sending...', tone: 'text-amber-700' }
  }
  return { dot: 'bg-slate-400', text: 'No deliveries yet', tone: 'text-muted' }
}

export function IntegrationsPage() {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const allowed = hasMinRole(user, 'controller')

  const summaryQuery = useQuery({
    queryKey: ['webhook-summary'],
    queryFn: getWebhookSummary,
    refetchInterval: REFRESH_MS,
    enabled: allowed,
  })

  const deliveriesQuery = useQuery({
    queryKey: ['webhook-deliveries'],
    queryFn: listWebhookDeliveries,
    refetchInterval: REFRESH_MS,
    enabled: allowed,
  })

  const retryMutation = useMutation({
    mutationFn: retryWebhookDelivery,
    onSuccess: (delivery) => {
      if (delivery.status === 'sent') {
        notifySuccess(`Delivered invoice ${delivery.invoice_number ?? ''}`.trim())
      } else {
        notifyError(`Retry failed: ${delivery.last_error ?? 'unknown error'}`)
      }
      void queryClient.invalidateQueries({ queryKey: ['webhook-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['webhook-deliveries'] })
    },
    onError: (error) => notifyError(`Retry failed: ${getApiErrorMessage(error)}`),
  })

  if (!allowed) {
    return (
      <section className="ff-card mx-auto max-w-3xl border-amber-200 bg-amber-50/40 p-6">
        <div className="flex items-start gap-3">
          <Shield className="mt-0.5 h-4 w-4 text-amber-700" />
          <p className="text-sm text-amber-900">Integrations are available to controllers only.</p>
        </div>
      </section>
    )
  }

  const summary = summaryQuery.data
  const health = connectionHealth(summary)

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div>
        <h2 className="ff-page-title">Integrations</h2>
        <p className="ff-page-subtitle">Outbound connections and their delivery history.</p>
      </div>

      <section className="ff-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-primary-600" />
            <h3 className="text-sm font-semibold text-slate-900">ERP webhook (n8n)</h3>
          </div>
          <span className={`flex items-center gap-2 text-sm font-medium ${health.tone}`}>
            <span className={`h-2.5 w-2.5 rounded-full ${health.dot}`} />
            {health.text}
          </span>
        </div>
        <p className="mt-2 text-xs text-muted">
          Sends approved invoices to{' '}
          <code className="rounded bg-canvas px-1.5 py-0.5 text-slate-800">
            {summary?.target_url ?? 'APPROVAL_WEBHOOK_URL not set'}
          </code>
        </p>
        <dl className="mt-5 grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg bg-canvas px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Last success</dt>
            <dd className="mt-1 text-sm font-medium text-slate-900">
              {summary?.last_success_at ? formatTime(summary.last_success_at) : 'Never'}
            </dd>
          </div>
          <div className="rounded-lg bg-canvas px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Failures (last 24h)</dt>
            <dd
              className={`mt-1 text-sm font-medium ${
                summary?.failures_24h ? 'text-red-700' : 'text-slate-900'
              }`}
            >
              {summary?.failures_24h ?? 0}
            </dd>
          </div>
          <div className="rounded-lg bg-canvas px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Last delivery</dt>
            <dd className="mt-1 text-sm font-medium text-slate-900">
              {formatTime(summary?.last_delivery_at ?? null)}
            </dd>
          </div>
        </dl>
        {summary?.last_status === 'failed' && summary.last_error ? (
          <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {summary.last_error}
            {summary.next_retry_at
              ? ` Next automatic retry at ${formatTime(summary.next_retry_at)}.`
              : ''}
          </p>
        ) : null}
      </section>

      <section className="ff-card p-6">
        <h3 className="text-sm font-semibold text-slate-900">Deliveries</h3>
        {deliveriesQuery.isLoading ? (
          <p className="mt-4 flex items-center text-sm text-muted">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading deliveries...
          </p>
        ) : !deliveriesQuery.data?.length ? (
          <p className="mt-4 text-sm text-muted">
            No deliveries yet. Approve an invoice to send one.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr className="border-b border-border">
                  <th className="py-2 pr-4 font-medium">Invoice</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Attempts</th>
                  <th className="py-2 pr-4 font-medium">Last attempt</th>
                  <th className="py-2 pr-4 font-medium">Last error</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {deliveriesQuery.data.map((delivery) => {
                  const status = DELIVERY_STATUS[delivery.status]
                  const retrying =
                    retryMutation.isPending && retryMutation.variables === delivery.id
                  return (
                    <tr key={delivery.id} className="border-b border-border last:border-0">
                      <td className="py-3 pr-4">
                        <p className="font-medium text-slate-900">
                          {delivery.invoice_number ?? delivery.invoice_id.slice(0, 8)}
                        </p>
                        <p className="text-xs text-muted">{delivery.vendor_name}</p>
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          title={delivery.status}
                          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${status.className}`}
                        >
                          {status.label}
                        </span>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-slate-900">{delivery.attempts}</td>
                      <td className="py-3 pr-4 text-slate-900">
                        {formatTime(delivery.last_attempt_at)}
                      </td>
                      <td className="max-w-sm py-3 pr-4 text-xs text-muted">
                        {delivery.status === 'sent' ? '—' : delivery.last_error ?? '—'}
                        {delivery.status === 'failed' && delivery.next_retry_at ? (
                          <span className="block">
                            Automatic retry at {formatTime(delivery.next_retry_at)}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-3 text-right">
                        {delivery.status === 'failed' ? (
                          <button
                            type="button"
                            disabled={retryMutation.isPending}
                            onClick={() => retryMutation.mutate(delivery.id)}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-primary-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-800 disabled:opacity-60"
                          >
                            {retrying ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <RotateCw className="h-3.5 w-3.5" />
                            )}
                            Retry now
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
