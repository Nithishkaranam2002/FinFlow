import { useQuery } from '@tanstack/react-query'
import { Activity, KeyRound, Server, Shield, UserCircle2 } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

interface HealthResponse {
  status: string
  version: string
  environment: string
  components?: Record<string, string>
}

export function SettingsPage() {
  const user = useAuthStore((s) => s.user)

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const apiRoot =
        import.meta.env.VITE_API_BASE_URL?.replace(/\/api\/v1\/?$/, '') ||
        'http://localhost:8000'
      const url = import.meta.env.DEV ? '/health' : `${apiRoot}/health`
      const response = await fetch(url)
      if (!response.ok) throw new Error('Health check failed')
      return (await response.json()) as HealthResponse
    },
    retry: 1,
  })

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h2 className="ff-page-title">Settings</h2>
        <p className="ff-page-subtitle">Account, security, and platform connectivity.</p>
      </div>

      <section className="ff-card p-6">
        <div className="flex items-center gap-2">
          <UserCircle2 className="h-4 w-4 text-primary-600" />
          <h3 className="text-sm font-semibold text-slate-900">Profile</h3>
        </div>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg bg-canvas px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Email</dt>
            <dd className="mt-1 text-sm font-medium text-slate-900">{user?.email}</dd>
          </div>
          <div className="rounded-lg bg-canvas px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Role</dt>
            <dd className="mt-1 text-sm font-medium capitalize text-slate-900">
              {user?.role?.replace('_', ' ')}
            </dd>
          </div>
          <div className="rounded-lg bg-canvas px-4 py-3 sm:col-span-2">
            <dt className="text-xs uppercase tracking-wide text-muted">Tenant ID</dt>
            <dd className="mt-1 font-mono text-xs text-slate-900">{user?.tenant_id}</dd>
          </div>
        </dl>
      </section>

      <section className="ff-card p-6">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-primary-600" />
          <h3 className="text-sm font-semibold text-slate-900">Platform Health</h3>
        </div>
        {healthQuery.isLoading ? (
          <p className="mt-4 text-sm text-muted">Checking API health...</p>
        ) : healthQuery.isError ? (
          <p className="mt-4 text-sm text-danger">Unable to reach API health endpoint.</p>
        ) : (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between rounded-lg bg-canvas px-4 py-3">
              <span className="text-sm text-muted">Overall status</span>
              <span className="ff-badge bg-emerald-100 text-emerald-800 capitalize">
                {healthQuery.data?.status}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {Object.entries(healthQuery.data?.components ?? {}).map(([name, status]) => (
                <div key={name} className="rounded-lg border border-border px-3 py-2">
                  <p className="text-xs capitalize text-muted">{name}</p>
                  <p className="mt-1 text-sm font-medium capitalize text-slate-900">{status}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted">
              API v{healthQuery.data?.version} · {healthQuery.data?.environment}
            </p>
          </div>
        )}
      </section>

      <section className="ff-card p-6">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-primary-600" />
          <h3 className="text-sm font-semibold text-slate-900">Integration</h3>
        </div>
        <p className="mt-3 text-sm text-muted">
          API base URL:{' '}
          <code className="rounded bg-canvas px-2 py-1 text-xs text-slate-800">
            {import.meta.env.VITE_API_BASE_URL || '/api/v1'}
          </code>
        </p>
      </section>

      <section className="ff-card border-amber-200 bg-amber-50/40 p-6">
        <div className="flex items-start gap-3">
          <Shield className="mt-0.5 h-4 w-4 text-amber-700" />
          <div>
            <h3 className="text-sm font-semibold text-amber-900">Security</h3>
            <p className="mt-2 text-sm text-amber-900/80">
              Sessions expire after 24 hours. All invoice and reconciliation actions are recorded
              in an immutable audit trail with actor role and timestamp.
            </p>
          </div>
        </div>
      </section>

      <div className="flex items-center gap-2 text-xs text-muted">
        <Activity className="h-3.5 w-3.5" />
        FinFlow production build · agentic invoice-to-reconciliation
      </div>
    </div>
  )
}
