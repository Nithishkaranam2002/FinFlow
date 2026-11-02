import type { ReactNode } from 'react'
import type { FraudFlag, Invoice, InvoiceStatus, User, UserRole } from '../types'

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

export const STATUS_LABELS: Record<InvoiceStatus, string> = {
  received: 'Received',
  extracting: 'Reading invoice',
  review_required: 'Review Required',
  matched: 'Matched',
  pending_approval: 'Pending Approval',
  approved: 'Approved',
  rejected: 'Rejected',
  paid: 'Paid',
}

const FRAUD_FLAG_LABELS: Record<string, string> = {
  THRESHOLD_GAMING: 'Just under approval limit',
  POTENTIAL_DUPLICATE: 'Possible duplicate',
  AMOUNT_ANOMALY: 'Unusual amount for vendor',
  HIGH_VELOCITY: 'Many invoices in a short time',
  BANK_ACCOUNT_RECENTLY_CHANGED: 'Bank details recently changed',
  UNKNOWN_VENDOR: 'Unknown vendor',
}

export function fraudFlagLabel(type: string): string {
  return FRAUD_FLAG_LABELS[type] ?? type.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

// Same fields the backend weighs for overall extraction confidence.
const ATTENTION_FIELD_LABELS: Record<string, string> = {
  invoice_number: 'invoice number',
  vendor_name: 'vendor name',
  total_amount: 'total amount',
  due_date: 'due date',
  line_items: 'line items',
}

function wholeDollars(value: unknown): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return 'approval'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

function describeFraudFlag(flag: FraudFlag): string {
  const details = flag as FraudFlag & Record<string, unknown>
  switch (flag.type) {
    case 'THRESHOLD_GAMING':
      return `Amount is just under the ${wholeDollars(details.threshold_amount)} approval limit, a common way to avoid senior approval`
    case 'POTENTIAL_DUPLICATE':
      return `Looks like a duplicate of invoice ${String(details.matched_invoice_number ?? 'already on file')}`
    case 'AMOUNT_ANOMALY':
      return `Amount is unusual for this vendor (${flag.description})`
    case 'HIGH_VELOCITY':
      return `Many invoices from this vendor in a short time (${flag.description})`
    case 'BANK_ACCOUNT_RECENTLY_CHANGED':
      return 'Vendor bank details changed recently, confirm them before paying'
    case 'UNKNOWN_VENDOR':
      return "Vendor name doesn't match any known vendor"
    default:
      return flag.description || fraudFlagLabel(flag.type)
  }
}

/** Plain-English reasons an invoice needs a human look, built only from saved checks. */
export function getAttentionReasons(invoice: Invoice): string[] {
  const reasons: string[] = []
  const flags = invoice.flags ?? {}

  const scores = getConfidenceScores(invoice)
  const unsure = Object.keys(ATTENTION_FIELD_LABELS).filter(
    (key) => key in scores && scores[key] < 0.75,
  )
  if (unsure.length) {
    reasons.push(`AI was not sure about: ${unsure.map((key) => ATTENTION_FIELD_LABELS[key]).join(', ')}`)
  }

  const fraudFlags = Array.isArray(flags.fraud_flags) ? (flags.fraud_flags as FraudFlag[]) : []
  fraudFlags.forEach((flag) => reasons.push(describeFraudFlag(flag)))

  if (Array.isArray(flags.math_issues)) {
    ;(flags.math_issues as string[]).forEach((issue) => reasons.push(issue))
  }

  const awaitingDecision = ['pending_approval', 'review_required', 'matched'].includes(invoice.status)
  if (awaitingDecision && flags.required_role === 'controller') {
    const fraudEscalated = fraudFlags.some((flag) => ['HIGH', 'CRITICAL'].includes(flag.severity))
    reasons.push(
      fraudEscalated
        ? 'Needs controller approval: a fraud check flagged this invoice'
        : 'Needs controller approval: amount is above the approver limit',
    )
  }

  if (!reasons.length && invoice.status === 'review_required') {
    reasons.push(String(flags.review_reason || 'Flagged for manual review'))
  }

  return reasons
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
  const approvableStatuses: InvoiceStatus[] = [
    'pending_approval',
    'review_required',
    'matched',
  ]
  if (!approvableStatuses.includes(invoice.status)) return false
  const required = ((invoice.flags?.required_role as UserRole) ?? 'approver') as UserRole
  if (invoice.status === 'matched' && !invoice.flags?.required_role) return false
  return ROLE_LEVEL[user.role] >= ROLE_LEVEL[required]
}

export function showsApprovalSection(invoice: Invoice): boolean {
  if (['pending_approval', 'review_required'].includes(invoice.status)) return true
  return invoice.status === 'matched' && Boolean(invoice.flags?.required_role)
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
