import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, Loader2, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { listInvoices } from '../../api/invoices'
import { manualMatch } from '../../api/reconciliation'
import { highlightGarbledText } from '../../lib/invoiceUtils'
import type { ReconciliationException } from '../../types'
import { formatCurrency, formatDate } from '../../lib/utils'
import { useAuthStore } from '../../store/authStore'

interface ExceptionQueueProps {
  items: ReconciliationException[]
  loading?: boolean
  onMatched?: () => void
}

export function ExceptionQueue({
  items,
  loading,
  onMatched,
}: ExceptionQueueProps) {
  const user = useAuthStore((s) => s.user)
  const canManualMatch =
    user?.role === 'controller' || user?.role === 'auditor'

  const [amountMin, setAmountMin] = useState('')
  const [amountMax, setAmountMax] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [matchLineId, setMatchLineId] = useState<string | null>(null)

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const amount = Number(item.amount)
      if (amountMin && amount < Number(amountMin)) return false
      if (amountMax && amount > Number(amountMax)) return false
      if (dateFrom && item.transaction_date < dateFrom) return false
      if (dateTo && item.transaction_date > dateTo) return false
      return true
    })
  }, [items, amountMin, amountMax, dateFrom, dateTo])

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-border bg-surface p-8 text-sm text-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading exceptions...
      </div>
    )
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted">Min amount</label>
          <input
            type="number"
            value={amountMin}
            onChange={(e) => setAmountMin(e.target.value)}
            placeholder="0"
            className="w-28 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted">Max amount</label>
          <input
            type="number"
            value={amountMax}
            onChange={(e) => setAmountMax(e.target.value)}
            placeholder="Any"
            className="w-28 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
          />
        </div>
      </div>

      {!filteredItems.length ? (
        <div className="rounded-xl border border-border bg-surface p-8 text-center text-sm text-muted">
          No unmatched bank lines in the queue.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item) => (
            <article
              key={item.line_id}
              className="rounded-xl border border-border bg-surface p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-900">
                    {highlightGarbledText(item.description)}
                  </p>
                  <p className="mt-1 text-sm text-muted">
                    {formatDate(item.transaction_date)} · Ref: {item.reference || 'N/A'}
                  </p>
                </div>
                <p className="text-lg font-semibold text-slate-900">
                  {formatCurrency(item.amount, item.currency)}
                </p>
              </div>
              <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50/50 px-4 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-amber-800">
                  Why it couldn't match
                </p>
                <p className="mt-1 text-sm text-slate-700">
                  {item.llm_explanation || item.exception_reason || 'No explanation available.'}
                </p>
              </div>
              {item.suggested_action ? (
                <p className="mt-2 text-xs font-medium text-primary-700">{item.suggested_action}</p>
              ) : null}
              {canManualMatch ? (
                <button
                  type="button"
                  onClick={() => setMatchLineId(item.line_id)}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary-900 px-3 py-2 text-xs font-medium text-white hover:bg-primary-800"
                >
                  <Link2 className="h-3.5 w-3.5" />
                  Manual Match
                </button>
              ) : null}
            </article>
          ))}
        </div>
      )}

      {matchLineId ? (
        <ManualMatchModal
          lineId={matchLineId}
          onClose={() => setMatchLineId(null)}
          onMatched={() => {
            setMatchLineId(null)
            onMatched?.()
          }}
        />
      ) : null}
    </>
  )
}

function ManualMatchModal({
  lineId,
  onClose,
  onMatched,
}: {
  lineId: string
  onClose: () => void
  onMatched: () => void
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null)
  const [notes, setNotes] = useState('')

  const invoicesQuery = useQuery({
    queryKey: ['invoices-manual-match', search],
    queryFn: () => listInvoices({ page: 1, page_size: 20 }),
  })

  const matchMutation = useMutation({
    mutationFn: () =>
      manualMatch(lineId, {
        invoice_id: selectedInvoiceId!,
        notes: notes || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reconciliation-exceptions'] })
      void queryClient.invalidateQueries({ queryKey: ['reconciliation-status'] })
      void queryClient.invalidateQueries({ queryKey: ['reconciliation-report'] })
      onMatched()
    },
  })

  const filtered = useMemo(() => {
    const items = invoicesQuery.data?.items ?? []
    if (!search.trim()) return items
    const q = search.toLowerCase()
    return items.filter(
      (inv) =>
        inv.invoice_number.toLowerCase().includes(q) ||
        String(inv.extracted_data?.vendor_name ?? '').toLowerCase().includes(q),
    )
  }, [invoicesQuery.data, search])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 bg-slate-900/50"
        onClick={onClose}
      />
      <div className="relative max-h-[80vh] w-full max-w-lg overflow-hidden rounded-2xl bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 className="text-lg font-semibold text-slate-900">Manual Match</h3>
          <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-canvas">
            <X className="h-5 w-5 text-muted" />
          </button>
        </div>
        <div className="space-y-4 overflow-y-auto p-5">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search invoices by number or vendor..."
              className="w-full rounded-lg border border-border py-2.5 pl-9 pr-3 text-sm outline-none focus:border-primary-500"
            />
          </div>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {invoicesQuery.isLoading ? (
              <p className="text-sm text-muted">Loading invoices...</p>
            ) : (
              filtered.map((invoice) => (
                <button
                  key={invoice.id}
                  type="button"
                  onClick={() => setSelectedInvoiceId(invoice.id)}
                  className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${
                    selectedInvoiceId === invoice.id
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-border hover:bg-canvas'
                  }`}
                >
                  <p className="text-sm font-medium text-slate-900">{invoice.invoice_number}</p>
                  <p className="text-xs text-muted">
                    {String(invoice.extracted_data?.vendor_name ?? 'Unknown vendor')} ·{' '}
                    {formatCurrency(invoice.amount, invoice.currency)}
                  </p>
                </button>
              ))
            )}
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes..."
            rows={2}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
          />
          <button
            type="button"
            disabled={!selectedInvoiceId || matchMutation.isPending}
            onClick={() => void matchMutation.mutateAsync()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-900 py-2.5 text-sm font-medium text-white hover:bg-primary-800 disabled:opacity-60"
          >
            {matchMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Link2 className="h-4 w-4" />
            )}
            Link Invoice
          </button>
          {matchMutation.isError ? (
            <p className="text-sm text-danger">Failed to create manual match. Try again.</p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
