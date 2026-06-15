import axios from 'axios'
import { logout as apiLogout } from './auth'
import { useAuthStore } from '../store/authStore'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    Accept: 'application/json',
  },
})

export function getApiErrorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg)
          }
          return String(item)
        })
        .join(', ')
    }
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearUser()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export async function logout() {
  try {
    await apiLogout()
  } finally {
    useAuthStore.getState().clearUser()
  }
}
