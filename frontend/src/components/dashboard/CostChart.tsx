import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { LLMCostSummary } from '../../types'

interface CostChartProps {
  data?: LLMCostSummary
  loading?: boolean
}

export function CostChart({ data, loading }: CostChartProps) {
  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center rounded-xl border border-border bg-surface text-sm text-muted">
        Loading cost data...
      </div>
    )
  }

  const chartData = (data?.cost_by_model ?? []).map((item) => ({
    model: item.model.length > 18 ? `${item.model.slice(0, 18)}…` : item.model,
    cost: Number(item.cost_usd.toFixed(4)),
    calls: item.calls,
  }))

  if (!chartData.length) {
    return (
      <div className="flex h-80 items-center justify-center rounded-xl border border-border bg-surface text-sm text-muted">
        No LLM cost data yet.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900">LLM Cost by Model</h3>
        <p className="text-xs text-muted">Last 30 days of model spend</p>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="model" tick={{ fontSize: 12 }} stroke="#64748b" />
            <YAxis tick={{ fontSize: 12 }} stroke="#64748b" />
            <Tooltip
              contentStyle={{
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
                fontSize: '12px',
              }}
            />
            <Bar dataKey="cost" fill="#1e40af" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
