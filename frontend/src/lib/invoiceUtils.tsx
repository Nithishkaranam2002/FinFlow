import type { ReactNode } from 'react'
import type { Invoice, InvoiceStatus, User, UserRole } from '../types'

const ROLE_LEVEL: Record<UserRole, number> = {
  ap_clerk: 1,
  approver: 2,
  controller: 3,
  auditor: 4,
}

export const STATUS_STYLES: Record<InvoiceStatus, string> = {
  received: 'bg-slate-100 text-slate-700',
  extracting: 'bg-blue-100 text-blue-800 animate-pulse',
  review_required: 'bg-amber-100 text-amber-800',
  matched: 'bg-cyan-100 text-cyan-800',
  pending_approval: 'bg-purple-100 text-purple-800',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  paid: 'bg-teal-100 text-teal-800',
}

export function getRiskScore(invoice: Invoice): number | null {
  const score = invoice.flags?.overall_risk_score
  return typeof score === 'number' ? score : null
}

export function getConfidenceScores(invoice: Invoice): Record<string, number> {
  const scores = invoice.flags?.confidence_scores
  return scores && typeof scores === 'object' ? (scores as Record<string, number>) : {}
}

export function canApproveInvoice(user: User | null, invoice: Invoice): boolean {
  if (!user) return false
  if (!['pending_approval', 'review_required'].includes(invoice.status)) return false
  const required = ((invoice.flags?.required_role as UserRole) ?? 'approver') as UserRole
  return ROLE_LEVEL[user.role] >= ROLE_LEVEL[required]
}

export interface ExtractedField {
  key: string
  label: string
  value: string
  confidence: number
}

export function getExtractedFields(invoice: Invoice): ExtractedField[] {
  const data = invoice.extracted_data ?? {}
  const scores = getConfidenceScores(invoice)

  const formatValue = (key: string, value: unknown): string => {
    if (value == null) return '—'
    if (key === 'line_items' && Array.isArray(value)) {
      return `${value.length} line item${value.length === 1 ? '' : 's'}`
    }
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
  }

  const fieldLabels: Record<string, string> = {
    invoice_number: 'Invoice Number',
    vendor_name: 'Vendor Name',
    vendor_email: 'Vendor Email',
    invoice_date: 'Invoice Date',
    due_date: 'Due Date',
    subtotal: 'Subtotal',
    tax_amount: 'Tax Amount',
    total_amount: 'Total Amount',
    currency: 'Currency',
    line_items: 'Line Items',
    payment_terms: 'Payment Terms',
    notes: 'Notes',
  }

  const keys = Object.keys(fieldLabels).filter(
    (key) => data[key] !== undefined && data[key] !== null && data[key] !== '',
  )

  return keys.map((key) => ({
    key,
    label: fieldLabels[key] ?? key.replace(/_/g, ' '),
    value: formatValue(key, data[key]),
    confidence: scores[key] ?? invoice.extraction_confidence ?? 1,
  }))
}

/** Highlight non-ASCII / garbled characters in bank descriptions. */
export function highlightGarbledText(text: string): ReactNode {
  const parts = text.split(/(\uFFFD|[^\x00-\x7F]+)/g).filter(Boolean)
  if (parts.length <= 1) return text

  return parts.map((part, index) => {
    const isGarbled = part === '\uFFFD' || /[^\x00-\x7F]/.test(part)
    if (isGarbled) {
      return (
        <mark
          key={`${part}-${index}`}
          className="rounded bg-amber-100 px-0.5 font-mono text-amber-900"
          title="Possible encoding issue"
        >
          {part}
        </mark>
      )
    }
    return part
  })
}
