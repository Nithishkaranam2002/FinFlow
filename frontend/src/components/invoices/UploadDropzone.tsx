import { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, CloudUpload, FileText, Loader2 } from 'lucide-react'
import { getInvoice } from '../../api/invoices'
import { formatCurrency, formatDate, StatusBadge } from '../../lib/utils'
import type { Invoice } from '../../types'

interface UploadDropzoneProps {
  onUpload: (file: File, onProgress: (percent: number) => void) => Promise<{ invoice_id: string }>
  accept?: string
  label?: string
  disabled?: boolean
}

const PROCESSING_STATUSES = new Set(['received', 'extracting'])

export function UploadDropzone({
  onUpload,
  accept = '.pdf,.png,.jpg,.jpeg,.webp,.tiff',
  label = 'Drop invoice PDF or image here, or click to browse',
  disabled = false,
}: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [processingId, setProcessingId] = useState<string | null>(null)

  const processingQuery = useQuery({
    queryKey: ['invoice-processing', processingId],
    queryFn: () => getInvoice(processingId!),
    enabled: Boolean(processingId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && PROCESSING_STATUSES.has(status) ? 2000 : false
    },
  })

  useEffect(() => {
    const invoice = processingQuery.data
    if (!invoice || PROCESSING_STATUSES.has(invoice.status)) return
    const timer = window.setTimeout(() => setProcessingId(null), 8000)
    return () => window.clearTimeout(timer)
  }, [processingQuery.data])

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      setProgress(0)
      try {
        const result = await onUpload(file, setProgress)
        setProcessingId(result.invoice_id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [onUpload],
  )

  const processingInvoice = processingQuery.data
  const isProcessing =
    processingInvoice && PROCESSING_STATUSES.has(processingInvoice.status)

  return (
    <div className="space-y-4">
      <label
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (disabled) return
          const file = e.dataTransfer.files[0]
          if (file) void handleFile(file)
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 transition-colors ${
          disabled
            ? 'cursor-not-allowed opacity-60'
            : dragging
              ? 'border-primary-500 bg-primary-50'
              : 'border-border bg-surface hover:border-primary-300 hover:bg-canvas'
        }`}
      >
        <input
          type="file"
          className="hidden"
          accept={accept}
          disabled={uploading || disabled}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleFile(file)
          }}
        />
        {uploading ? (
          <Loader2 className="h-10 w-10 animate-spin text-primary-600" />
        ) : (
          <CloudUpload className="h-10 w-10 text-primary-600" />
        )}
        <p className="mt-4 text-sm font-medium text-slate-900">{label}</p>
        <p className="mt-1 flex items-center gap-1 text-xs text-muted">
          <FileText className="h-3 w-3" />
          PDF, PNG, JPG, WEBP, TIFF
        </p>
        {uploading ? (
          <div className="mt-4 w-full max-w-xs">
            <div className="mb-1 flex justify-between text-xs text-muted">
              <span>Uploading...</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-primary-600 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        ) : null}
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      </label>

      {processingId && processingInvoice ? (
        <ProcessingCard invoice={processingInvoice} isProcessing={Boolean(isProcessing)} />
      ) : null}
    </div>
  )
}

function ProcessingCard({
  invoice,
  isProcessing,
}: {
  invoice: Invoice
  isProcessing: boolean
}) {
  return (
    <article className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-900">
            {isProcessing ? 'Processing...' : 'Extraction complete'}
          </p>
          <p className="mt-1 text-xs text-muted">
            Invoice {invoice.invoice_number || invoice.id.slice(0, 8)}
          </p>
        </div>
        {isProcessing ? (
          <Loader2 className="h-5 w-5 animate-spin text-primary-600" />
        ) : (
          <CheckCircle2 className="h-5 w-5 text-success" />
        )}
      </div>
      <div className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted">Amount</p>
          <p className="font-medium">{formatCurrency(invoice.amount, invoice.currency)}</p>
        </div>
        <div>
          <p className="text-xs text-muted">Due Date</p>
          <p className="font-medium">{formatDate(invoice.due_date)}</p>
        </div>
        <div>
          <p className="text-xs text-muted">Status</p>
          <div className="mt-1">
            <StatusBadge status={invoice.status} />
          </div>
        </div>
      </div>
      {!isProcessing && invoice.extracted_data ? (
        <p className="mt-3 text-xs text-muted">
          Vendor: {String(invoice.extracted_data.vendor_name ?? '—')} · Confidence:{' '}
          {invoice.extraction_confidence != null
            ? `${Math.round(invoice.extraction_confidence * 100)}%`
            : '—'}
        </p>
      ) : null}
    </article>
  )
}
