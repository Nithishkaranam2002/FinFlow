import { apiClient } from './client'
import type {
  AuditLogEntry,
  Invoice,
  InvoiceListResponse,
  InvoiceStatus,
} from '../types'

export async function login(email: string, password: string) {
  const body = new URLSearchParams()
  body.append('username', email)
  body.append('password', password)
  const { data } = await apiClient.post<{ access_token: string; token_type: string }>(
    '/auth/login',
    body,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  )
  return data
}

export async function fetchMe(token?: string) {
  const { data } = await apiClient.get('/auth/me', {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
  return data
}

export async function listInvoices(params?: {
  status?: InvoiceStatus
  vendor_id?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}) {
  const { data } = await apiClient.get<InvoiceListResponse>('/invoices/', { params })
  return data
}

export async function getInvoice(id: string) {
  const { data } = await apiClient.get<Invoice>(`/invoices/${id}`)
  return data
}

export async function uploadInvoice(
  file: File,
  vendorId: string,
  onProgress?: (percent: number) => void,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('vendor_id', vendorId)
  const { data } = await apiClient.post<{ invoice_id: string; status: string }>(
    '/invoices/upload',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (!onProgress || !event.total) return
        onProgress(Math.round((event.loaded / event.total) * 100))
      },
    },
  )
  return data
}

export async function approveInvoice(id: string, notes?: string) {
  const { data } = await apiClient.patch<Invoice>(`/invoices/${id}/approve`, { notes })
  return data
}

export async function rejectInvoice(id: string, reason: string) {
  const { data } = await apiClient.patch<Invoice>(`/invoices/${id}/reject`, { reason })
  return data
}

export async function getInvoiceAuditTrail(id: string) {
  const { data } = await apiClient.get<AuditLogEntry[]>(`/invoices/${id}/audit-trail`)
  return data
}

export async function correctExtraction(
  id: string,
  corrections: Record<string, unknown>,
  notes?: string,
) {
  const { data } = await apiClient.patch<Invoice>(`/invoices/${id}/correct-extraction`, {
    corrections,
    notes,
  })
  return data
}
