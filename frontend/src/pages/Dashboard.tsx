import { useQuery } from '@tanstack/react-query'
import { fetchDashboardStats, fetchLLMCosts, fetchMatchRate } from '../api/dashboard'
import { CostChart } from '../components/dashboard/CostChart'
import { ProcessingTimeline } from '../components/dashboard/ProcessingTimeline'
import { StatsCards } from '../components/dashboard/StatsCards'
import { MatchRateChart } from '../components/reconciliation/MatchRateChart'

export function DashboardPage() {
  const statsQuery = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: fetchDashboardStats,
  })
  const matchRateQuery = useQuery({
    queryKey: ['dashboard-match-rate'],
    queryFn: fetchMatchRate,
  })
  const costsQuery = useQuery({
    queryKey: ['dashboard-llm-costs'],
    queryFn: fetchLLMCosts,
  })

  return (
    <div className="space-y-6">
      <StatsCards stats={statsQuery.data} loading={statsQuery.isLoading} />

      <div className="grid gap-6 xl:grid-cols-2">
        <MatchRateChart data={matchRateQuery.data} loading={matchRateQuery.isLoading} />
        <CostChart data={costsQuery.data} loading={costsQuery.isLoading} />
      </div>

      <ProcessingTimeline stats={statsQuery.data} loading={statsQuery.isLoading} />

      {(statsQuery.isError || matchRateQuery.isError || costsQuery.isError) && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
          Some dashboard data failed to load. Ensure the API is running on port 8000.
        </div>
      )}
    </div>
  )
}
