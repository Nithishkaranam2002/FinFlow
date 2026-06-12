import { apiClient } from './client'
import type { DashboardStats, LLMCostSummary, MatchRateResponse } from '../types'

export async function fetchDashboardStats() {
  const { data } = await apiClient.get<DashboardStats>('/dashboard/stats')
  return data
}

export async function fetchMatchRate() {
  const { data } = await apiClient.get<MatchRateResponse>('/dashboard/match-rate')
  return data
}

export async function fetchLLMCosts() {
  const { data } = await apiClient.get<LLMCostSummary>('/dashboard/llm-costs')
  return data
}
