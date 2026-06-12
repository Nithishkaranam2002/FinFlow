import { ChevronLeft, ChevronRight, Eye, Loader2, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Invoice, InvoiceStatus, Vendor } from '../../types'
import {
  ConfidenceBadge,
  formatCurrency,
  formatDate,
  RiskScoreBar,
  StatusBadge,
} from '../../lib/utils'
import { SlideOver } from '../ui/SlideOver'
import { InvoiceDetailPanel } from './InvoiceDetail'

const STATUS_OPTIONS: Array<{ value: '' | InvoiceStatus; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'received', label: 'Received' },
  { value: 'extracting', label: 'Extracting' },
  { value: 'review_required', label: 'Review Required' },
  { value: 'matched', label: 'Matched' },
  { value: 'pending_approval', label: 'Pending Approval' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'paid', label: 'Paid' },
]

interface InvoiceTableProps {
  invoices: Invoice[]
  vendors: Vendor[]
  total: number
  page: number
  pageSize: number
  loading?: boolean
  statusFilter: InvoiceStatus | ''
  vendorSearch: string
  dateFrom: string
  dateTo: string
  onStatusFilterChange: (value: InvoiceStatus | '') => void
  onVendorSearchChange: (value: string) => void
  onDateFromChange: (value: string) => void
  onDateToChange: (value: string) => void
  onPageChange: (page: number) => void
  onRefresh?: () => void
}

export function InvoiceTable({
  invoices,
  vendors,
  total,
  page,
  pageSize,
  loading,
  statusFilter,
  vendorSearch,
  dateFrom,
  dateTo,
  onStatusFilterChange,
  onVendorSearchChange,
  onDateFromChange,
  onDateToChange,
  onPageChange,
  onRefresh,
}: InvoiceTableProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const vendorMap = useMemo(
    () => new Map(vendors.map((vendor) => [vendor.id, vendor.name])),
    [vendors],
  )

  const filteredInvoices = useMemo(() => {
    if (!vendorSearch.trim()) return invoices
    const query = vendorSearch.toLowerCase()
    return invoices.filter((invoice) => {
      const vendorName = vendorMap.get(invoice.vendor_id)?.toLowerCase() ?? ''
      const extractedVendor = String(invoice.extracted_data?.vendor_name ?? '').toLowerCase()
      return (
        vendorName.includes(query) ||
        extractedVendor.includes(query) ||
        invoice.invoice_number.toLowerCase().includes(query)
      )
    })
  }, [invoices, vendorMap, vendorSearch])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const selectedInvoice = filteredInvoices.find((inv) => inv.id === selectedId)

  return (
    <>
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4 shadow-sm">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value as InvoiceStatus | '')}
              className="rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-primary-500"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.label} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 block text-xs font-medium text-muted">Vendor search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                value={vendorSearch}
                onChange={(e) => onVendorSearchChange(e.target.value)}
                placeholder="Search vendor or invoice #..."
                className="w-full rounded-lg border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-primary-500"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => onDateFromChange(e.target.value)}
              className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => onDateToChange(e.target.value)}
              className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500"
            />
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
          {loading ? (
            <div className="flex items-center justify-center gap-2 p-12 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading invoices...
            </div>
          ) : !filteredInvoices.length ? (
            <div className="p-12 text-center text-sm text-muted">No invoices found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-border">
                <thead className="bg-canvas">
                  <tr>
                    {[
                      'Invoice #',
                      'Vendor',
                      'Amount',
                      'Due Date',
                      'Status',
                      'Risk Score',
                      'Confidence',
                      'Actions',
                    ].map((header) => (
                      <th
                        key={header}
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted"
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredInvoices.map((invoice) => {
                    const riskScore =
                      typeof invoice.flags?.overall_risk_score === 'number'
                        ? invoice.flags.overall_risk_score
                        : null

                    return (
                      <tr
                        key={invoice.id}
                        onClick={() => setSelectedId(invoice.id)}
                        className="cursor-pointer transition-colors hover:bg-primary-50/40"
                      >
                        <td className="px-4 py-3 text-sm font-medium text-primary-800">
                          {invoice.invoice_number}
                        </td>
                        <td className="px-4 py-3 text-sm text-slate-900">
                          {vendorMap.get(invoice.vendor_id) ??
                            (invoice.extracted_data?.vendor_name as string) ??
                            '—'}
                        </td>
                        <td className="px-4 py-3 text-sm text-slate-900">
                          {formatCurrency(invoice.amount, invoice.currency)}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted">
                          {formatDate(invoice.due_date)}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={invoice.status} />
                        </td>
                        <td className="px-4 py-3">
                          {riskScore != null ? (
                            <RiskScoreBar score={riskScore} />
                          ) : (
                            <span className="text-xs text-muted">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <ConfidenceBadge confidence={invoice.extraction_confidence} />
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedId(invoice.id)
                            }}
                            className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-primary-700 hover:bg-canvas"
                          >
                            <Eye className="h-3.5 w-3.5" />
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-between border-t border-border bg-canvas px-4 py-3">
            <p className="text-xs text-muted">
              Showing page {page} of {totalPages} · {total} total
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => onPageChange(page + 1)}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <SlideOver
        open={Boolean(selectedId)}
        onClose={() => setSelectedId(null)}
        title={selectedInvoice?.invoice_number ?? 'Invoice Detail'}
      >
        {selectedId ? (
          <InvoiceDetailPanel
            invoiceId={selectedId}
            onUpdated={() => {
              onRefresh?.()
            }}
          />
        ) : null}
      </SlideOver>
    </>
  )
}
