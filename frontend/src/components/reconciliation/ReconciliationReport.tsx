import { Download, Loader2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { downloadReconciliationReport } from '../../api/reconciliation'
import type { ReconciliationReport, ReconciliationStatus } from '../../types'

interface ReconciliationReportProps {
  status?: ReconciliationStatus
  report?: ReconciliationReport
  loading?: boolean
}

const MATCH_COLORS = {
  exact: '#059669',
  fuzzy: '#d97706',
  llm: '#2563eb',
  unmatched: '#94a3b8',
}

export function ReconciliationReportPanel({
  status,
  report,
  loading,
}: ReconciliationReportProps) {
  const [downloading, setDownloading] = useState(false)

  const donutData = useMemo(() => {
    if (!status || !status.total_lines) return []
    const total = status.total_lines
    return [
      { name: 'Exact', value: status.exact_matched, pct: (status.exact_matched / total) * 100 },
      { name: 'Fuzzy', value: status.fuzzy_matched, pct: (status.fuzzy_matched / total) * 100 },
      { name: 'LLM', value: status.llm_matched, pct: (status.llm_matched / total) * 100 },
      {
        name: 'Unmatched',
        value: status.unmatched_lines,
        pct: (status.unmatched_lines / total) * 100,
      },
    ].filter((item) => item.value > 0)
  }, [status])

  const llmReasoning = useMemo(() => {
    if (!report) return []
    const fromLines = report.lines
      .filter((line) => line.llm_reasoning)
      .map((line) => ({
        id: line.line_id,
        description: line.description,
        reasoning: line.llm_reasoning!,
        matchType: line.match_type,
      }))
    const fromUnmatched = report.unmatched_explanations.map((text, index) => ({
      id: `unmatched-${index}`,
      description: 'Unmatched line',
      reasoning: text,
      matchType: 'unmatched' as const,
    }))
    return [...fromLines, ...fromUnmatched]
  }, [report])

  async function handleDownload() {
    if (!status?.statement_id) return
    setDownloading(true)
    try {
      await downloadReconciliationReport(status.statement_id)
    } finally {
      setDownloading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-border bg-surface p-8 text-sm text-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading reconciliation report...
      </div>
    )
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center text-sm text-muted">
        Upload a bank statement to begin reconciliation.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Reconciliation Summary</h3>
          {report ? (
            <p className="text-xs text-muted">
              {report.filename} · Generated{' '}
              {new Date(report.generated_at).toLocaleString('en-US')}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          disabled={downloading || status.status !== 'completed'}
          onClick={() => void handleDownload()}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-primary-800 hover:bg-canvas disabled:opacity-50"
        >
          {downloading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Download Report
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm lg:col-span-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Match Distribution</p>
          {donutData.length ? (
            <div className="mt-2 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={donutData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                  >
                    {donutData.map((entry, index) => (
                      <Cell
                        key={entry.name}
                        fill={
                          [MATCH_COLORS.exact, MATCH_COLORS.fuzzy, MATCH_COLORS.llm, MATCH_COLORS.unmatched][
                            index
                          ] ?? MATCH_COLORS.unmatched
                        }
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value, name, item) => [
                      `${value} lines (${(item.payload as { pct: number }).pct.toFixed(1)}%)`,
                      name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-8 text-center text-sm text-muted">No data yet</p>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:col-span-3 lg:grid-cols-2">
          {[
            ['Total Lines', status.total_lines],
            ['Match Rate', `${status.match_rate.toFixed(1)}%`],
            ['Exact', `${status.total_lines ? ((status.exact_matched / status.total_lines) * 100).toFixed(1) : 0}%`],
            ['Fuzzy', `${status.total_lines ? ((status.fuzzy_matched / status.total_lines) * 100).toFixed(1) : 0}%`],
            ['LLM', `${status.total_lines ? ((status.llm_matched / status.total_lines) * 100).toFixed(1) : 0}%`],
            ['Unmatched', `${status.total_lines ? ((status.unmatched_lines / status.total_lines) * 100).toFixed(1) : 0}%`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {llmReasoning.length ? (
        <section className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <h4 className="text-sm font-semibold text-slate-900">LLM Reasoning Transparency</h4>
          <p className="mt-1 text-xs text-muted">
            Plain-English explanations for matching decisions and exceptions
          </p>
          <div className="mt-4 space-y-3">
            {llmReasoning.map((item) => (
              <article
                key={item.id}
                className="rounded-lg border border-border bg-canvas px-4 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-slate-900">{item.description}</p>
                  {item.matchType ? (
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-700">
                      {String(item.matchType).replace(/_/g, ' ')}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-sm text-muted">{item.reasoning}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
