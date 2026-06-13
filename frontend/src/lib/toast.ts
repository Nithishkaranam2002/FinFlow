import { toast } from 'sonner'
import { getApiErrorMessage } from '../api/client'

export function notifySuccess(message: string) {
  toast.success(message)
}

export function notifyError(message: string, error?: unknown) {
  const detail = error ? getApiErrorMessage(error, message) : message
  toast.error(detail)
}

export function notifyInfo(message: string) {
  toast.info(message)
}
