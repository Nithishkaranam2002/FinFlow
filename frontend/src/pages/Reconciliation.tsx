import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getReconciliationReport,
  getReconciliationStatus,
  listExceptions,
  uploadStatement,
} from '../api/reconciliation'
import { BankStatementUpload } from '../components/reconciliation/BankStatementUpload'
import { ExceptionQueue } from '../components/reconciliation/ExceptionQueue'
import { MatchRateChart } from '../components/reconciliation/MatchRateChart'
import { ReconciliationReportPanel } from '../components/reconciliation/ReconciliationReport'

export function ReconciliationPage() {
  const queryClient = useQueryClient()
  const [statementId, setStatementId] = useState<string | null>(null)

  const statusQuery = useQuery({
    queryKey: ['reconciliation-status', statementId],
    queryFn: () => getReconciliationStatus(statementId!),
    enabled: Boolean(statementId),
    refetchInterval: (query) =>
      query.state.data?.status === 'processing' ? 2000 : false,
  })

  const reportQuery = useQuery({
    queryKey: ['reconciliation-report', statementId],
    queryFn: () => getReconciliationReport(statementId!),
    enabled: Boolean(statementId) && statusQuery.data?.status === 'completed',
  })

  const exceptionsQuery = useQuery({
    queryKey: ['reconciliation-exceptions', statementId],
    queryFn: () =>
      listExceptions({
        statement_id: statementId ?? undefined,
        page: 1,
        page_size: 50,
      }),
    enabled: Boolean(statementId),
  })

  const uploadMutation = useMutation({
    mutationFn: ({
      file,
      onProgress,
    }: {
      file: File
      onProgress: (percent: number) => void
    }) => uploadStatement(file, onProgress),
    onSuccess: (data) => {
      setStatementId(data.statement_id)
      void queryClient.invalidateQueries({ queryKey: ['reconciliation-exceptions'] })
    },
  })

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Bank Reconciliation</h2>
        <p className="text-sm text-muted">
          Upload statements, monitor match rates, and resolve unmatched exceptions.
        </p>
      </div>

      <BankStatementUpload
        onUpload={async (file, onProgress) =>
          uploadMutation.mutateAsync({ file, onProgress })
        }
      />

      <MatchRateChart
        report={reportQuery.data}
        status={statusQuery.data}
        loading={statusQuery.isLoading}
        variant="line"
      />

      <ReconciliationReportPanel
        status={statusQuery.data}
        report={reportQuery.data}
        loading={statusQuery.isLoading || reportQuery.isLoading}
      />

      <section>
        <h3 className="mb-4 text-sm font-semibold text-slate-900">Exception Queue</h3>
        <ExceptionQueue
          items={exceptionsQuery.data?.items ?? []}
          loading={exceptionsQuery.isLoading}
          onMatched={() => {
            void queryClient.invalidateQueries({ queryKey: ['reconciliation-exceptions'] })
            void queryClient.invalidateQueries({ queryKey: ['reconciliation-status'] })
            void queryClient.invalidateQueries({ queryKey: ['reconciliation-report'] })
          }}
        />
      </section>
    </div>
  )
}
