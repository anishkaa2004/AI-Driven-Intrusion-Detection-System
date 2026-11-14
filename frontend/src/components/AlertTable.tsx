import { Link } from "react-router-dom";
import type { Alert } from "../types";
import { DemoBadge, SeverityBadge, SourceBadge, StatusBadge, ago, categoryLabel, td, th } from "./ui";

export default function AlertTable({ alerts, compact = false }: { alerts: Alert[]; compact?: boolean }) {
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="border-b border-slate-100 dark:border-slate-800">
          <tr>
            <th className={th}>Severity</th>
            <th className={th}>Alert</th>
            {!compact && <th className={th}>Device</th>}
            <th className={th}>Source</th>
            <th className={th}>Status</th>
            <th className={th}>Last seen</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {alerts.map((a) => (
            <tr key={a.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
              <td className={td}><SeverityBadge severity={a.severity} /></td>
              <td className={td}>
                <Link to={`/alerts/${a.id}`} className="font-medium text-slate-800 hover:text-teal-700 hover:underline dark:text-slate-100 dark:hover:text-teal-400">
                  {a.title}
                </Link>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                  <span className="capitalize">{categoryLabel(a.category)}</span>
                  {a.occurrence_count > 1 && <span>· seen {a.occurrence_count}×</span>}
                  {a.is_demo && <DemoBadge />}
                </div>
              </td>
              {!compact && <td className={td + " text-slate-600 dark:text-slate-300"}>{a.device_name}</td>}
              <td className={td}><SourceBadge source={a.detection_source} /></td>
              <td className={td}><StatusBadge status={a.status} /></td>
              <td className={td + " whitespace-nowrap text-slate-500"} title={new Date(a.last_seen_at).toLocaleString()}>{ago(a.last_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
