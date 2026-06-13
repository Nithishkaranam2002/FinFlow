import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Clock3,
  Loader2,
  Pencil,
  ShieldAlert,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import {
  approveInvoice,
  correctExtraction,
  getInvoice,
  getInvoiceAuditTrail,
  rejectInvoice,
} from '../../api/invoices'
import { getApiErrorMessage } from '../../api/client'
import { listVendors } from '../../api/vendors'
import { notifyError, notifySuccess } from '../../lib/toast'
import {
  canApproveInvoice,
  getExtractedFields,
  getRiskScore,
  showsApprovalSection,
} from '../../lib/invoiceUtils'
import type { FraudFlag, Invoice } from '../../types'
import { formatCurrency, StatusBadge } from '../../lib/utils'
import { useAuthStore } from '../../store/authStore'
import { FraudFlagCard } from './FraudFlagBadge'

interface InvoiceDetailPanelProps {
  invoiceId: string
  onUpdated?: () => void
}

function getFraudFlagsFromInvoice(invoice: Invoice): FraudFlag[] {
  const flags = invoice.flags?.fraud_flags
  return Array.isArray(flags) ? (flags as FraudFlag[]) : []
}

export function InvoiceDetailPanel({ invoiceId, onUpdated }: InvoiceDetailPanelProps) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [approvalNotes, setApprovalNotes] = useState('')
  const [rejectReason, setRejectReason] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [editingField, setEditingField] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const invoiceQuery = useQuery({
    queryKey: ['invoice', invoiceId],
    queryFn: () => getInvoice(invoiceId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'extracting' ||
        status === 'received' ||
        status === 'matched'
        ? 2000
        : false
    },
  })

  const auditQuery = useQuery({
    queryKey: ['invoice-audit', invoiceId],
    queryFn: () => getInvoiceAuditTrail(invoiceId),
  })

  const vendorsQuery = useQuery({
    queryKey: ['vendors'],
    queryFn: listVendors,
  })

  const approveMutation = useMutation({
    mutationFn: () => approveInvoice(invoiceId, approvalNotes || undefined),
    onSuccess: () => {
      setActionError(null)
      notifySuccess('Invoice approved successfully')
      void queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] })
      void queryClient.invalidateQueries({ queryKey: ['invoice-audit', invoiceId] })
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      onUpdated?.()
    },
    onError: (error) => {
      const message = `Approval failed: ${getApiErrorMessage(error)}`
      setActionError(message)
      notifyError(message)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => rejectInvoice(invoiceId, rejectReason),
    onSuccess: () => {
      setActionError(null)
      notifySuccess('Invoice rejected')
      void queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] })
      void queryClient.invalidateQueries({ queryKey: ['invoice-audit', invoiceId] })
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      onUpdated?.()
    },
    onError: (error) => {
      const message = `Rejection failed: ${getApiErrorMessage(error)}`
      setActionError(message)
      notifyError(message)
    },
  })

  const correctMutation = useMutation({
    mutationFn: ({ field, value }: { field: string; value: string }) =>
      correctExtraction(invoiceId, { [field]: value }),
    onSuccess: () => {
      setEditingField(null)
      void queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] })
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      onUpdated?.()
    },
  })

  if (invoiceQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-muted">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading invoice...
      </div>
    )
  }

  if (invoiceQuery.isError || !invoiceQuery.data) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
        Failed to load invoice details.
      </div>
    )
  }

  const invoice = invoiceQuery.data
  const fraudFlags = getFraudFlagsFromInvoice(invoice)
  const riskScore = getRiskScore(invoice)
  const extractedFields = getExtractedFields(invoice)
  const vendorName =
    vendorsQuery.data?.find((v) => v.id === invoice.vendor_id)?.name ??
    (invoice.extracted_data?.vendor_name as string | undefined) ??
    invoice.vendor_id.slice(0, 8)
  const canApprove = canApproveInvoice(user, invoice)

  return (
    <div className="space-y-6">
      <header className="rounded-xl border border-border bg-canvas p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Invoice</p>
            <h3 className="mt-1 text-xl font-semibold text-slate-900">{invoice.invoice_number}</h3>
            <p className="mt-1 text-sm text-muted">{vendorName}</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-semibold text-slate-900">
              {formatCurrency(invoice.amount, invoice.currency)}
            </p>
            <div className="mt-2 flex justify-end">
              <StatusBadge status={invoice.status} />
            </div>
          </div>
        </div>
        {riskScore != null && riskScore > 0.5 ? (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            Elevated risk score: {riskScore.toFixed(2)}
          </div>
        ) : null}
      </header>

      <section>
        <h4 className="text-sm font-semibold text-slate-900">Extracted Data</h4>
        <div className="mt-3 space-y-2">
          {extractedFields.length ? (
            extractedFields.map((field) => {
              const lowConfidence = field.confidence < 0.75
              const isEditing = editingField === field.key

              return (
                <div
                  key={field.key}
                  className={`rounded-lg border px-4 py-3 ${
                    lowConfidence
                      ? 'border-amber-200 bg-amber-50/60'
                      : 'border-border bg-surface'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted">
                          {field.label}
                        </p>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${
                            lowConfidence
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {Math.round(field.confidence * 100)}%
                        </span>
                      </div>
                      {isEditing ? (
                        <div className="mt-2 flex gap-2">
                          <input
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            className="flex-1 rounded-lg border border-border px-3 py-1.5 text-sm outline-none focus:border-primary-500"
                          />
                          <button
                            type="button"
                            disabled={correctMutation.isPending}
                            onClick={() =>
                              void correctMutation.mutateAsync({ field: field.key, value: editValue })
                            }
                            className="rounded-lg bg-primary-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-800 disabled:opacity-60"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingField(null)}
                            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:bg-canvas"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <p className="mt-1 text-sm font-medium text-slate-900">{field.value}</p>
                      )}
                    </div>
                    {lowConfidence && !isEditing ? (
                      <button
                        type="button"
                        title="Correct extraction"
                        onClick={() => {
                          setEditingField(field.key)
                          setEditValue(String(invoice.extracted_data?.[field.key] ?? field.value))
                        }}
                        className="rounded-lg p-2 text-amber-700 hover:bg-amber-100"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    ) : null}
                  </div>
                </div>
              )
            })
          ) : (
            <p className="text-sm text-muted">No extracted data available yet.</p>
          )}
        </div>
      </section>

      <section>
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-warning" />
          <h4 className="text-sm font-semibold text-slate-900">Fraud Flags</h4>
        </div>
        <div className="mt-3 space-y-3">
          {fraudFlags.length ? (
            fraudFlags.map((flag, index) => (
              <FraudFlagCard key={`${flag.type}-${index}`} flag={flag} />
            ))
          ) : (
            <p className="rounded-lg border border-border bg-canvas px-4 py-3 text-sm text-muted">
              No fraud flags detected.
            </p>
          )}
        </div>
      </section>

      {showsApprovalSection(invoice) ? (
        <section className="rounded-xl border border-purple-200 bg-purple-50/40 p-5">
          <h4 className="text-sm font-semibold text-slate-900">Approval</h4>
          {canApprove ? (
            <div className="mt-4 space-y-4">
              {actionError ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
                  {actionError}
                </div>
              ) : null}
              <textarea
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Optional approval notes..."
                rows={3}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
              />
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  disabled={approveMutation.isPending || rejectMutation.isPending}
                  onClick={() => approveMutation.mutate()}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {approveMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Approving...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4" />
                      Approve
                    </>
                  )}
                </button>
                <div className="flex flex-1 flex-wrap items-end gap-2">
                  <input
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Rejection reason (required)"
                    className="min-w-[200px] flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-primary-500"
                  />
                  <button
                    type="button"
                    disabled={
                      rejectMutation.isPending ||
                      approveMutation.isPending ||
                      !rejectReason.trim()
                    }
                    onClick={() => rejectMutation.mutate()}
                    className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-danger hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {rejectMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Rejecting...
                      </>
                    ) : (
                      <>
                        <XCircle className="h-4 w-4" />
                        Reject
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted">
              Requires {(invoice.flags?.required_role as string) ?? 'approver'} role or higher to
              approve.
            </p>
          )}
        </section>
      ) : null}

      <section>
        <div className="flex items-center gap-2">
          <Clock3 className="h-4 w-4 text-primary-600" />
          <h4 className="text-sm font-semibold text-slate-900">Audit Trail</h4>
        </div>
        {auditQuery.isLoading ? (
          <p className="mt-4 text-sm text-muted">Loading audit trail...</p>
        ) : (
          <ol className="relative mt-4 space-y-0 border-l border-border pl-6">
            {(auditQuery.data ?? []).map((entry) => (
              <li key={entry.id} className="relative pb-6 last:pb-0">
                <span className="absolute -left-[25px] top-1 flex h-3 w-3 rounded-full border-2 border-surface bg-primary-600" />
                <p className="text-sm font-medium capitalize text-slate-900">
                  {entry.action.replace(/_/g, ' ')}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {entry.actor_role} ·{' '}
                  {new Date(entry.created_at).toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                  })}
                </p>
                {entry.reason ? (
                  <p className="mt-1 text-xs text-muted">{entry.reason}</p>
                ) : null}
              </li>
            ))}
            {!auditQuery.data?.length ? (
              <li className="text-sm text-muted">No audit events recorded.</li>
            ) : null}
          </ol>
        )}
      </section>
    </div>
  )
}
