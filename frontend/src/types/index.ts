export type InvoiceStatus =
  | 'received'
  | 'extracting'
  | 'review_required'
  | 'matched'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'paid'

export type UserRole = 'ap_clerk' | 'approver' | 'controller' | 'auditor'

export type MatchType =
  | 'exact'
  | 'fuzzy'
  | 'llm_judgment'
  | 'manual'
  | 'unmatched'

export type StatementStatus = 'processing' | 'completed' | 'failed'

export interface User {
  id: string
  tenant_id: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface Vendor {
  id: string
  tenant_id: string
  name: string
  email?: string | null
}

export interface LineItem {
  description: string
  quantity: string | number
  unit_price: string | number
  total: string | number
}

export interface FraudFlag {
  type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  description: string
}

export interface Invoice {
  id: string
  tenant_id: string
  vendor_id: string
  invoice_number: string
  amount: string | number
  currency: string
  due_date: string | null
  line_items: LineItem[] | Record<string, unknown>[]
  status: InvoiceStatus
  extraction_confidence: number | null
  extracted_data: Record<string, unknown> | null
  flags: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface InvoiceListResponse {
  items: Invoice[]
  total: number
  page: number
  page_size: number
}

export interface Payment {
  id: string
  tenant_id: string
  invoice_id: string
  amount: string | number
  status: string
  payment_reference?: string | null
}

export interface ReconciliationMatch {
  id: string
  tenant_id: string
  bank_line_id: string
  invoice_id: string | null
  payment_id: string | null
  match_type: MatchType
  confidence_score: number | null
  llm_reasoning: string | null
  matched_by: string | null
  matched_at: string | null
  created_at: string
}

export interface StatusCount {
  status: InvoiceStatus
  count: number
}

export interface DashboardStats {
  invoices_today: StatusCount[]
  invoices_this_week: StatusCount[]
  invoices_this_month: StatusCount[]
  average_processing_time_hours: number
  exception_rate: number
  cost_per_invoice_usd: number
}

export interface MatchRateDataPoint {
  date: string
  total_lines: number
  matched_lines: number
  match_rate: number
}

export interface MatchRateResponse {
  data_points: MatchRateDataPoint[]
}

export interface LLMCostByModel {
  model: string
  cost_usd: number
  calls: number
}

export interface LLMCostByDay {
  date: string
  cost_usd: number
  calls: number
}

export interface LLMCostSummary {
  total_cost_usd: number
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  average_cost_per_invoice_usd: number
  invoice_count: number
  cost_by_day: LLMCostByDay[]
  cost_by_model: LLMCostByModel[]
  cost_by_agent: { agent: string; cost_usd: number; calls: number }[]
}

export interface ReconciliationException {
  line_id: string
  transaction_date: string
  description: string
  amount: string | number
  currency: string
  reference: string | null
  llm_explanation: string | null
  exception_reason: string | null
  suggested_action: string | null
}

export interface ReconciliationExceptionListResponse {
  items: ReconciliationException[]
  total: number
  page: number
  page_size: number
}

export interface ReconciliationStatus {
  statement_id: string
  status: StatementStatus
  total_lines: number
  matched_lines: number
  pending_lines: number
  unmatched_lines: number
  match_rate: number
  exact_matched: number
  fuzzy_matched: number
  llm_matched: number
  manual_matched: number
}

export interface BankStatementUploadResponse {
  statement_id: string
  line_count: number
  status: StatementStatus
}

export interface ReconciliationReport {
  statement_id: string
  filename: string
  status: StatementStatus
  generated_at: string
  summary: Record<string, unknown>
  lines: Array<{
    line_id: string
    transaction_date: string
    description: string
    amount: string | number
    currency: string
    match_type: MatchType | null
    confidence_score: number | null
    invoice_id: string | null
    payment_id: string | null
    llm_reasoning: string | null
    exception_reason: string | null
  }>
  unmatched_explanations: string[]
}

export interface AuditLogEntry {
  id: string
  entity_type: string
  entity_id: string
  action: string
  actor_id: string
  actor_role: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  reason: string | null
  ip_address: string | null
  created_at: string
}
