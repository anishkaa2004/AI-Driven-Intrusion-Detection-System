import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useFetch } from "../app/useFetch";
import { Button, Card, Empty, ErrorBox, PageHeader, Spinner, fmtTime, selectInline, td, th } from "../components/ui";
import { api } from "../services/api";
import type { AuditEntry, Page } from "../types";

const PREFIXES = ["", "auth", "user", "device", "alert", "settings", "report"];

export default function AuditPage() {
  const { isAdmin } = useAuth();
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading } = useFetch(() => api.get<Page<AuditEntry>>("/audit-logs", { action, page, page_size: 50 }), [action, page]);
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / 50));

  return (
    <>
      <PageHeader title="Audit log" subtitle={isAdmin ? "All significant user, device and configuration actions" : "Actions you performed"}
        actions={
          <select className={selectInline} value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} aria-label="Action type">
            {PREFIXES.map((p) => <option key={p} value={p}>{p ? `${p}.*` : "All actions"}</option>)}
          </select>
        } />
      <ErrorBox error={error} />
      <Card actions={loading && <Spinner />} title={data ? `${data.total.toLocaleString()} entries` : "Entries"}>
        {data?.items.length ? (
          <>
            <div className="-mx-4 overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="border-b border-slate-100 dark:border-slate-800">
                  <tr><th className={th}>Time</th><th className={th}>Actor</th><th className={th}>Action</th><th className={th}>Target</th><th className={th}>Details</th><th className={th}>IP</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.items.map((e) => (
                    <tr key={e.id}>
                      <td className={td + " whitespace-nowrap text-xs text-slate-500"}>{fmtTime(e.created_at, true)}</td>
                      <td className={td + " text-xs"}>{e.actor_email ?? <span className="text-slate-400">system / agent</span>}</td>
                      <td className={td + " font-mono text-xs"}>{e.action}</td>
                      <td className={td + " text-xs"}>
                        {e.target_type === "alert" ? <Link className="text-teal-700 hover:underline dark:text-teal-400" to={`/alerts/${e.target_id}`}>alert #{e.target_id}</Link>
                          : e.target_type ? `${e.target_type} ${e.target_id ?? ""}` : "—"}
                      </td>
                      <td className={td + " max-w-xs truncate font-mono text-xs text-slate-500"} title={JSON.stringify(e.metadata_json)}>
                        {Object.keys(e.metadata_json).length ? JSON.stringify(e.metadata_json) : ""}
                      </td>
                      <td className={td + " font-mono text-xs text-slate-500"}>{e.ip_address}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm text-slate-500">
              <span>Page {page} of {pages}</span>
              <div className="flex gap-2">
                <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          </>
        ) : data ? <Empty title="No audit entries" /> : null}
      </Card>
    </>
  );
}
