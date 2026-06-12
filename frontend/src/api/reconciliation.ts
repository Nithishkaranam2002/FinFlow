import { apiClient } from './client'
import type {
  BankStatementUploadResponse,
  ReconciliationExceptionListResponse,
  ReconciliationMatch,
  ReconciliationReport,
  ReconciliationStatus,
} from '../types'

export async function uploadStatement(file: File, onProgress?: (percent: number) => void) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<BankStatementUploadResponse>(
    '/reconciliation/upload-statement',
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

export async function getReconciliationStatus(statementId: string) {
  const { data } = await apiClient.get<ReconciliationStatus>(
    `/reconciliation/status/${statementId}`,
  )
  return data
}

export async function listExceptions(params?: { page?: number; page_size?: number; statement_id?: string }) {
  const { data } = await apiClient.get<ReconciliationExceptionListResponse>(
    '/reconciliation/exceptions',
    { params },
  )
  return data
}

export async function getReconciliationReport(statementId: string) {
  const { data } = await apiClient.get<ReconciliationReport>(
    `/reconciliation/report/${statementId}`,
  )
  return data
}

export async function listReconciliationMatches(params?: { page?: number; match_type?: string }) {
  const { data } = await apiClient.get<{ items: ReconciliationMatch[]; total: number }>(
    '/reconciliation/',
    { params },
  )
  return data
}

export async function manualMatch(
  lineId: string,
  payload: { invoice_id: string; payment_id?: string; notes?: string },
) {
  const { data } = await apiClient.patch<ReconciliationMatch>(
    `/reconciliation/exceptions/${lineId}/manual-match`,
    payload,
  )
  return data
}

export async function downloadReconciliationReport(statementId: string) {
  const { data } = await apiClient.get<ReconciliationReport>(
    `/reconciliation/report/${statementId}`,
  )
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `reconciliation-report-${statementId.slice(0, 8)}.json`
  link.click()
  URL.revokeObjectURL(url)
  return data
}
