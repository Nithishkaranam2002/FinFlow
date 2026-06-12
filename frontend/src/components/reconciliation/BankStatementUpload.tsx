import { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, CloudUpload, FileSpreadsheet, Loader2 } from 'lucide-react'
import { getReconciliationStatus } from '../../api/reconciliation'
import type { ReconciliationStatus } from '../../types'

interface BankStatementUploadProps {
  onUpload: (file: File, onProgress: (percent: number) => void) => Promise<{
    statement_id: string
    line_count: number
    status: string
  }>
  disabled?: boolean
}

export function BankStatementUpload({ onUpload, disabled = false }: BankStatementUploadProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [statementId, setStatementId] = useState<string | null>(null)

  const statusQuery = useQuery({
    queryKey: ['reconciliation-upload-status', statementId],
    queryFn: () => getReconciliationStatus(statementId!),
    enabled: Boolean(statementId),
    refetchInterval: (query) =>
      query.state.data?.status === 'processing' ? 2000 : false,
  })

  useEffect(() => {
    if (statusQuery.data?.status === 'completed' || statusQuery.data?.status === 'failed') {
      const timer = window.setTimeout(() => setStatementId(null), 10000)
      return () => window.clearTimeout(timer)
    }
  }, [statusQuery.data?.status])

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      setProgress(0)
      try {
        const result = await onUpload(file, setProgress)
        setStatementId(result.statement_id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [onUpload],
  )

  const status = statusQuery.data

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
          accept=".csv,.mt940,.sta,.940,text/csv,text/plain"
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
        <p className="mt-4 text-sm font-medium text-slate-900">
          Drop bank statement CSV or MT940 here, or click to browse
        </p>
        <p className="mt-1 flex items-center gap-1 text-xs text-muted">
          <FileSpreadsheet className="h-3 w-3" />
          CSV, MT940, STA formats supported
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

      {status ? <StatementStatusCard status={status} /> : null}
    </div>
  )
}

function StatementStatusCard({ status }: { status: ReconciliationStatus }) {
  const isProcessing = status.status === 'processing'
  const isFailed = status.status === 'failed'

  return (
    <article className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-900">
            {isProcessing
              ? 'Processing statement...'
              : isFailed
                ? 'Processing failed'
                : 'Reconciliation complete'}
          </p>
          <p className="mt-1 text-xs text-muted">
            {status.total_lines} lines · {status.match_rate.toFixed(1)}% match rate
          </p>
        </div>
        {isProcessing ? (
          <Loader2 className="h-5 w-5 animate-spin text-primary-600" />
        ) : isFailed ? null : (
          <CheckCircle2 className="h-5 w-5 text-success" />
        )}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {[
          ['Exact', status.exact_matched],
          ['Fuzzy', status.fuzzy_matched],
          ['LLM', status.llm_matched],
          ['Unmatched', status.unmatched_lines],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-canvas px-3 py-2">
            <p className="text-xs text-muted">{label}</p>
            <p className="font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>
    </article>
  )
}
