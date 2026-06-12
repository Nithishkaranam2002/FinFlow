import { apiClient } from './client'
import type { Vendor } from '../types'

export async function listVendors() {
  const { data } = await apiClient.get<Vendor[]>('/vendors/')
  return data
}
