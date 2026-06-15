import { apiClient } from './client'
import type { User } from '../types'

export async function login(email: string, password: string) {
  const body = new URLSearchParams()
  body.append('username', email)
  body.append('password', password)
  const { data } = await apiClient.post<{ user: User; token_type: string }>(
    '/auth/login',
    body,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  )
  return data
}

export async function logout() {
  await apiClient.post('/auth/logout')
}

export async function fetchMe() {
  const { data } = await apiClient.get<User>('/auth/me')
  return data
}
