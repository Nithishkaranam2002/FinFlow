import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  title: string
  subtitle?: string
}

export function Layout({ title, subtitle }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} subtitle={subtitle} />
        <main className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
