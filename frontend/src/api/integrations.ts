import { apiClient } from './client'
import type { WebhookDelivery, WebhookSummary } from '../types'

export async function getWebhookSummary() {
  const { data } = await apiClient.get<WebhookSummary>('/integrations/webhook/summary')
  return data
}

export async function listWebhookDeliveries() {
  const { data } = await apiClient.get<WebhookDelivery[]>('/integrations/webhook/deliveries')
  return data
}

export async function retryWebhookDelivery(id: string) {
  const { data } = await apiClient.post<WebhookDelivery>(
    `/integrations/webhook/deliveries/${id}/retry`,
  )
  return data
}
