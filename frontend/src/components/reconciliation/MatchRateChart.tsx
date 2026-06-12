import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MatchRateResponse, ReconciliationReport, ReconciliationStatus } from '../../types'

interface MatchRateChartProps {
  data?: MatchRateResponse
  report?: ReconciliationReport
  status?: ReconciliationStatus
  loading?: boolean
  variant?: 'line' | 'area'
}

function buildChartData(report?: ReconciliationReport) {
  if (!report?.lines?.length) return []

  const byDate = new Map<
    string,
    { exact: number; fuzzy: number; llm: number; total: number }
  >()

  for (const line of report.lines) {
    const date = line.transaction_date
    const entry = byDate.get(date) ?? { exact: 0, fuzzy: 0, llm: 0, total: 0 }
    entry.total += 1
    if (line.match_type === 'exact') entry.exact += 1
    if (line.match_type === 'fuzzy') entry.fuzzy += 1
    if (line.match_type === 'llm_judgment') entry.llm += 1
    byDate.set(date, entry)
  }

  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, counts]) => ({
      date: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      exactPct: counts.total ? Math.round((counts.exact / counts.total) * 100) : 0,
      fuzzyPct: counts.total ? Math.round((counts.fuzzy / counts.total) * 100) : 0,
      llmPct: counts.total ? Math.round((counts.llm / counts.total) * 100) : 0,
    }))
}

export function MatchRateChart({
  data,
  report,
  status,
  loading,
  variant = 'line',
}: MatchRateChartProps) {
  const chartData = useMemo(() => buildChartData(report), [report])

  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center rounded-xl border border-border bg-surface text-sm text-muted">
        Loading match rate chart...
      </div>
    )
  }

  if (data?.data_points?.length) {
    const dashboardData = data.data_points.map((point) => ({
      date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      exactPct: point.match_rate,
      fuzzyPct: 0,
      llmPct: 0,
    }))
    return renderOverallChart(dashboardData)
  }

  if (!chartData.length) {
    if (status && status.total_lines > 0) {
      const total = status.total_lines || 1
      const fallback = [
        {
          date: 'Current',
          exactPct: Math.round((status.exact_matched / total) * 100),
          fuzzyPct: Math.round((status.fuzzy_matched / total) * 100),
          llmPct: Math.round((status.llm_matched / total) * 100),
        },
      ]
      return renderChart(fallback, variant)
    }

    return (
      <div className="flex h-80 items-center justify-center rounded-xl border border-border bg-surface text-sm text-muted">
        Upload a statement to view match type trends.
      </div>
    )
  }

  return renderChart(chartData, variant)
}

function renderOverallChart(
  data: Array<{ date: string; exactPct: number; fuzzyPct: number; llmPct: number }>,
) {
  const tooltipStyle = {
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '12px',
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900">Reconciliation Match Rate</h3>
        <p className="text-xs text-muted">Daily match rate over the last 30 days</p>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#64748b" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} stroke="#64748b" />
            <Tooltip contentStyle={tooltipStyle} />
            <Line
              type="monotone"
              dataKey="exactPct"
              stroke="#1e40af"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#1e40af' }}
              name="Match Rate %"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function renderChart(
  data: Array<{ date: string; exactPct: number; fuzzyPct: number; llmPct: number }>,
  variant: 'line' | 'area',
) {
  const tooltipStyle = {
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '12px',
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900">Match Type Breakdown</h3>
        <p className="text-xs text-muted">Exact, fuzzy, and LLM judgment match rates over time</p>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          {variant === 'area' ? (
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#64748b" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} stroke="#64748b" />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Area
                type="monotone"
                dataKey="exactPct"
                stackId="1"
                stroke="#059669"
                fill="#059669"
                fillOpacity={0.6}
                name="Exact %"
              />
              <Area
                type="monotone"
                dataKey="fuzzyPct"
                stackId="1"
                stroke="#d97706"
                fill="#d97706"
                fillOpacity={0.6}
                name="Fuzzy %"
              />
              <Area
                type="monotone"
                dataKey="llmPct"
                stackId="1"
                stroke="#2563eb"
                fill="#2563eb"
                fillOpacity={0.6}
                name="LLM %"
              />
            </AreaChart>
          ) : (
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#64748b" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} stroke="#64748b" />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Line
                type="monotone"
                dataKey="exactPct"
                stroke="#059669"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Exact %"
              />
              <Line
                type="monotone"
                dataKey="fuzzyPct"
                stroke="#d97706"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Fuzzy %"
              />
              <Line
                type="monotone"
                dataKey="llmPct"
                stroke="#2563eb"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="LLM %"
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
