import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { AlertStatus, Health, Severity } from "../types";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Card({ title, actions, children, className }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "warn" | "bad" | "ok" }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className={cx("tabular mt-1 text-2xl font-semibold",
        tone === "bad" && "text-red-600 dark:text-red-400",
        tone === "warn" && "text-amber-600 dark:text-amber-400",
        tone === "ok" && "text-teal-700 dark:text-teal-400")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}

const SEV_STYLE: Record<Severity, string> = {
  critical: "bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-300 dark:bg-fuchsia-950 dark:text-fuchsia-300 dark:ring-fuchsia-800",
  high: "bg-red-100 text-red-800 ring-red-300 dark:bg-red-950 dark:text-red-300 dark:ring-red-800",
  medium: "bg-amber-100 text-amber-800 ring-amber-300 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-800",
  low: "bg-sky-100 text-sky-800 ring-sky-300 dark:bg-sky-950 dark:text-sky-300 dark:ring-sky-800",
  info: "bg-slate-100 text-slate-700 ring-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700",
};
export const SEV_COLOR: Record<Severity, string> = {
  critical: "#c026d3", high: "#dc2626", medium: "#d97706", low: "#0284c7", info: "#64748b",
};

const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={cx(pill, SEV_STYLE[severity], "capitalize")}>{severity}</span>;
}

const STATUS_STYLE: Record<AlertStatus, string> = {
  new: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/50 dark:text-red-300 dark:ring-red-900",
  acknowledged: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:ring-amber-900",
  investigating: "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-950/50 dark:text-violet-300 dark:ring-violet-900",
  resolved: "bg-teal-50 text-teal-700 ring-teal-200 dark:bg-teal-950/50 dark:text-teal-300 dark:ring-teal-900",
  false_positive: "bg-slate-50 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700",
};

export const statusLabel = (s: string) => s.replace(/_/g, " ");

export function StatusBadge({ status }: { status: AlertStatus }) {
  return <span className={cx(pill, STATUS_STYLE[status], "capitalize")}>{statusLabel(status)}</span>;
}

const HEALTH: Record<Health, { label: string; dot: string; cls: string }> = {
  online: { label: "Reporting", dot: "bg-teal-500", cls: "text-teal-700 dark:text-teal-300" },
  stale: { label: "Stale", dot: "bg-amber-500", cls: "text-amber-700 dark:text-amber-300" },
  offline: { label: "Not reporting", dot: "bg-red-500", cls: "text-red-700 dark:text-red-300" },
  never_seen: { label: "Never seen", dot: "bg-slate-400", cls: "text-slate-600 dark:text-slate-400" },
  pending: { label: "Awaiting enrollment", dot: "bg-sky-500", cls: "text-sky-700 dark:text-sky-300" },
  revoked: { label: "Revoked", dot: "bg-slate-500", cls: "text-slate-500 line-through" },
};

export function HealthBadge({ health }: { health: Health }) {
  const h = HEALTH[health];
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs font-medium", h.cls)}>
      <span className={cx("h-2 w-2 rounded-full", h.dot, health === "online" && "animate-pulse")} />
      {h.label}
    </span>
  );
}

export function SourceBadge({ source }: { source: string }) {
  const label = { rule: "Rule", ml: "ML model", anomaly: "Anomaly", combined: "Rule + ML" }[source] ?? source;
  return <span className={cx(pill, "bg-white text-slate-700 ring-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700")}>{label}</span>;
}

export function DemoBadge() {
  return <span className={cx(pill, "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300 dark:ring-indigo-900")} title="Generated by the replay tool; not live traffic">demo data</span>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; size?: "sm" | "md" };

export function Button({ variant = "secondary", size = "md", className, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" && "bg-teal-600 text-white hover:bg-teal-700",
        variant === "secondary" && "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        variant === "ghost" && "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
        className,
      )}
    />
  );
}

export const inputCls =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-teal-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900";

export const selectInline = inputCls.replace("w-full ", "") + " w-auto";

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-4 py-10 text-center">
      <div className="text-sm font-medium text-slate-700 dark:text-slate-300">{title}</div>
      {children && <div className="max-w-md text-sm text-slate-500 dark:text-slate-400">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-teal-600" role="status" aria-label="Loading" />;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">{error}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export const th = "px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400";
export const td = "px-3 py-2 align-top";

// ---------------------------------------------------------------- formatting
export function fmtTime(iso: string | null | undefined, withSeconds = false) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
  });
}

export function ago(iso: string | null | undefined) {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function fmtBytes(n: number | null | undefined) {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1000 && i < u.length - 1) {
    v /= 1000;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

export const fmtNum = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());
const CATEGORY_LABELS: Record<string, string> = {
  dos: "DoS / flood",
  dns_anomaly: "DNS anomaly",
  port_scan: "port scan",
  brute_force: "brute force",
  web_attack: "web attack",
  botnet: "botnet",
};
export const categoryLabel = (c: string) => CATEGORY_LABELS[c] ?? c.replace(/^ml_/, "").replace(/_/g, " ");

/** Privacy-conscious default: hide the host part of IPs unless revealed. */
export function maskIp(ip: string | null, reveal: boolean) {
  if (!ip) return "—";
  if (reveal) return ip;
  if (ip.includes(":")) return ip.split(":").slice(0, 2).join(":") + ":…";
  const p = ip.split(".");
  return `${p[0]}.${p[1]}.x.x`;
}
