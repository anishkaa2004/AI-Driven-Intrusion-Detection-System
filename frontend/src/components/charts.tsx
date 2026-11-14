import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtBytes } from "./ui";

const AXIS = { fontSize: 11, fill: "#94a3b8" };
const GRID = "rgba(148,163,184,0.18)";
const tooltipStyle = {
  contentStyle: { background: "rgb(15 23 42 / 0.92)", border: "none", borderRadius: 8, color: "#e2e8f0", fontSize: 12 },
  labelStyle: { color: "#cbd5e1" },
  itemStyle: { color: "#e2e8f0" },
};

function timeTick(hours: number) {
  return (iso: string) => {
    const d = new Date(iso);
    return hours > 48
      ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };
}

export function TrafficChart({ data, hours, height = 240 }: {
  data: { t: string; flows: number; alerts?: number }[];
  hours: number;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="flowFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#14b8a6" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="t" tickFormatter={timeTick(hours)} tick={AXIS} minTickGap={40} axisLine={false} tickLine={false} />
        <YAxis yAxisId="f" tick={AXIS} allowDecimals={false} axisLine={false} tickLine={false} />
        <YAxis yAxisId="a" orientation="right" tick={AXIS} allowDecimals={false} axisLine={false} tickLine={false} hide={data.every((d) => !d.alerts)} />
        <Tooltip {...tooltipStyle} labelFormatter={(l) => new Date(String(l)).toLocaleString()} />
        <Area yAxisId="f" type="monotone" dataKey="flows" name="Flows" stroke="#0d9488" strokeWidth={1.8} fill="url(#flowFill)" isAnimationActive={false} />
        {data.some((d) => d.alerts !== undefined) && (
          <Bar yAxisId="a" dataKey="alerts" name="Alerts" fill="#dc2626" barSize={6} radius={[2, 2, 0, 0]} isAnimationActive={false} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function BytesChart({ data, height = 200 }: {
  data: { t: string; bytes_in: number; bytes_out: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="t" tickFormatter={timeTick(1)} tick={AXIS} minTickGap={40} axisLine={false} tickLine={false} />
        <YAxis tick={AXIS} tickFormatter={(v) => fmtBytes(Number(v))} axisLine={false} tickLine={false} width={56} />
        <Tooltip {...tooltipStyle} formatter={(v) => fmtBytes(Number(v))} labelFormatter={(l) => new Date(String(l)).toLocaleTimeString()} />
        <Bar dataKey="bytes_in" name="Inbound" stackId="b" fill="#0d9488" isAnimationActive={false} />
        <Bar dataKey="bytes_out" name="Outbound" stackId="b" fill="#6366f1" radius={[2, 2, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars for small categorical breakdowns. Pure CSS: crisp and theme-aware. */
export function HBars({ rows, color, format = (n: number) => n.toLocaleString(), empty = "No data in this period" }: {
  rows: { label: string; value: number; color?: string }[];
  color?: string;
  format?: (n: number) => string;
  empty?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length || rows.every((r) => r.value === 0)) {
    return <div className="py-6 text-center text-sm text-slate-500">{empty}</div>;
  }
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.label} className="text-sm">
          <div className="mb-0.5 flex justify-between gap-2">
            <span className="truncate capitalize text-slate-600 dark:text-slate-300">{r.label}</span>
            <span className="tabular text-slate-500">{format(r.value)}</span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800">
            <div className="h-1.5 rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: r.color ?? color ?? "#0d9488" }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const rowTotals = matrix.map((r) => r.reduce((a, b) => a + b, 0) || 1);
  return (
    <div className="overflow-x-auto">
      <table className="text-xs tabular">
        <thead>
          <tr>
            <th className="p-1.5 text-left font-normal text-slate-500">true ↓ / predicted →</th>
            {labels.map((l) => <th key={l} className="p-1.5 font-medium text-slate-600 dark:text-slate-300">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={labels[i]}>
              <th className="p-1.5 text-left font-medium text-slate-600 dark:text-slate-300">{labels[i]}</th>
              {row.map((v, j) => {
                const share = v / rowTotals[i];
                const diag = i === j;
                return (
                  <td key={j} className="p-0.5">
                    <div className="min-w-14 rounded px-2 py-1.5 text-center"
                      title={`${(share * 100).toFixed(1)}% of true ${labels[i]}`}
                      style={{
                        background: diag ? `rgba(13,148,136,${0.12 + share * 0.75})` : v ? `rgba(220,38,38,${0.08 + share * 0.8})` : "transparent",
                        color: share > 0.55 ? "white" : undefined,
                      }}>
                      {v.toLocaleString()}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
