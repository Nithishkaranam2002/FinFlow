import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect } from 'react'

interface SlideOverProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
}

export function SlideOver({ open, onClose, title, children }: SlideOverProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close panel"
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-2xl flex-col bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title ?? 'Details'}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-muted transition-colors hover:bg-canvas hover:text-slate-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
      </aside>
    </div>
  )
}
