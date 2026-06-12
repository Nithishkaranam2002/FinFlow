import { useAuthStore } from '../store/authStore'

export function SettingsPage() {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Settings</h2>
        <p className="text-sm text-muted">Account and workspace preferences.</p>
      </div>

      <section className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900">Profile</h3>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between border-b border-border pb-3">
            <dt className="text-muted">Email</dt>
            <dd className="font-medium text-slate-900">{user?.email}</dd>
          </div>
          <div className="flex justify-between border-b border-border pb-3">
            <dt className="text-muted">Role</dt>
            <dd className="font-medium capitalize text-slate-900">
              {user?.role?.replace('_', ' ')}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted">Tenant ID</dt>
            <dd className="font-mono text-xs text-slate-900">{user?.tenant_id}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900">API Configuration</h3>
        <p className="mt-2 text-sm text-muted">
          Frontend API base URL:{' '}
          <code className="rounded bg-canvas px-2 py-1 text-xs">
            {import.meta.env.VITE_API_BASE_URL || '/api/v1'}
          </code>
        </p>
      </section>
    </div>
  )
}
