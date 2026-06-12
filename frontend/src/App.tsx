import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { DashboardPage } from './pages/Dashboard'
import { InvoiceDetailPage } from './pages/InvoiceDetail'
import { InvoicesPage } from './pages/Invoices'
import { LoginPage } from './pages/Login'
import { ReconciliationPage } from './pages/Reconciliation'
import { SettingsPage } from './pages/Settings'
import { useAuthStore } from './store/authStore'

function AuthenticatedRedirect({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (token) {
    return <Navigate to="/" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <AuthenticatedRedirect>
            <LoginPage />
          </AuthenticatedRedirect>
        }
      />

      <Route element={<ProtectedRoute />}>
        <Route
          path="/"
          element={<Layout title="Dashboard" subtitle="Operational overview and AI cost insights" />}
        >
          <Route index element={<DashboardPage />} />
        </Route>
        <Route
          path="/invoices"
          element={<Layout title="Invoices" subtitle="Upload, review, and approve vendor invoices" />}
        >
          <Route index element={<InvoicesPage />} />
          <Route path=":invoiceId" element={<InvoiceDetailPage />} />
        </Route>
        <Route
          path="/reconciliation"
          element={
            <Layout title="Reconciliation" subtitle="Match bank statements to payments and invoices" />
          }
        >
          <Route index element={<ReconciliationPage />} />
        </Route>
        <Route path="/settings" element={<Layout title="Settings" subtitle="Account preferences" />}>
          <Route index element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
