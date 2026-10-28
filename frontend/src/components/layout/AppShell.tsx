import {
  GitCompareArrows,
  History,
  LayoutDashboard,
  Library,
  Settings,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'Workspace', icon: LayoutDashboard, end: true },
  { to: '/references', label: 'References', icon: Library },
  { to: '/candidates', label: 'A/B', icon: GitCompareArrows },
  { to: '/jobs', label: 'Jobs', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell() {
  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-3 pb-20 pt-4 sm:px-6 lg:px-8 lg:pb-8 lg:pt-6">
      <header className="mb-6 flex items-end justify-between gap-4 animate-fade-up">
        <div>
          <p className="font-display text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
            Music AI
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            Local studio · brief canvas · role-locks · candidates
          </p>
        </div>
        <div className="hidden items-center gap-2 sm:flex">
          <span className="rounded-md border border-line bg-white/70 px-2.5 py-1 text-[11px] uppercase tracking-wider text-ink-muted">
            collaborative
          </span>
          <span className="rounded-md border border-line bg-white/70 px-2.5 py-1 text-[11px] uppercase tracking-wider text-ink-muted">
            scratch
          </span>
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-6 lg:flex-row">
        <nav
          className="hidden w-48 shrink-0 flex-col gap-1 lg:flex"
          aria-label="Primary"
        >
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-accent text-white'
                    : 'text-ink-muted hover:bg-paper-2 hover:text-ink',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <main className="min-w-0 flex-1 animate-fade-up [animation-delay:60ms]">
          <Outlet />
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-paper/95 backdrop-blur lg:hidden"
        aria-label="Mobile"
      >
        <div className="mx-auto grid max-w-7xl grid-cols-5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex flex-col items-center gap-1 px-1 py-2.5 text-[10px]',
                  isActive ? 'text-accent' : 'text-ink-muted',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
