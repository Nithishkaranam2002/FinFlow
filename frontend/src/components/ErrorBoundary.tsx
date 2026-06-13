import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { hasError: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('FinFlow UI error', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
          <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center shadow-xl">
            <h1 className="text-xl font-semibold text-white">Something went wrong</h1>
            <p className="mt-3 text-sm text-slate-400">
              An unexpected error occurred. Refresh the page or contact your administrator.
            </p>
            <button
              type="button"
              className="mt-6 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              onClick={() => window.location.assign('/')}
            >
              Return to dashboard
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
