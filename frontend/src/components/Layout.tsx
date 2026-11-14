import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useLive } from "../app/live";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: "M3 12h4l3-8 4 16 3-8h4" },
  { to: "/live", label: "Live monitoring", icon: "M2 12h3m14 0h3M12 2v3m0 14v3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" },
  { to: "/threats", label: "Threat center", icon: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM12 8v4m0 4h.01" },
  { to: "/history", label: "Incident history", icon: "M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5m4-1v5l3 3" },
  { to: "/devices", label: "Devices", icon: "M4 5h16v10H4zM2 19h20M9 15v4m6-4v4" },
  { to: "/analytics", label: "ML analytics", icon: "M4 20V10m6 10V4m6 16v-7m4 7H2" },
  { to: "/settings", label: "Settings", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" },
  { to: "/audit", label: "Audit log", icon: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9 2 2 4-4" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function LiveIndicator() {
  const { status } = useLive();
  const map = {
    live: { dot: "bg-teal-500", text: "Live updates" },
    connecting: { dot: "bg-slate-400", text: "Connecting…" },
    reconnecting: { dot: "bg-amber-500", text: "Reconnecting — polling every 30s" },
  }[status];
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400" title="Dashboard connection only; device health is shown per device">
      <span className={cx("h-2 w-2 rounded-full", map.dot)} />
      {map.text}
    </span>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen md:flex">
      <aside className={cx(
        "fixed inset-y-0 left-0 z-30 w-60 border-r border-slate-200 bg-white px-3 py-4 transition-transform dark:border-slate-800 dark:bg-slate-900 md:sticky md:top-0 md:h-screen md:shrink-0 md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full",
      )}>
        <div className="mb-6 flex items-center gap-2 px-2">
          <img src="/shield.svg" alt="" className="h-7 w-7" />
          <div>
            <div className="text-sm font-bold tracking-tight">AI-IDS</div>
            <div className="text-[11px] text-slate-500">Intrusion detection</div>
          </div>
        </div>
        <nav className="space-y-0.5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => cx(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm",
                isActive ? "bg-teal-50 font-medium text-teal-800 dark:bg-teal-950/50 dark:text-teal-300"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
              )}>
              <Icon d={n.icon} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <p className="absolute bottom-4 left-3 right-3 text-[11px] leading-snug text-slate-400">
          Educational prototype. Alerts are indicators requiring investigation, not proof of an attack.
        </p>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/30 md:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-2.5 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
          <button className="rounded p-1 md:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Icon d="M4 6h16M4 12h16M4 18h16" />
          </button>
          <LiveIndicator />
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-slate-600 dark:text-slate-300 sm:inline">{user?.email}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs capitalize text-slate-600 dark:bg-slate-800 dark:text-slate-300">{user?.role}</span>
            <button onClick={logout} className="text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">Sign out</button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
