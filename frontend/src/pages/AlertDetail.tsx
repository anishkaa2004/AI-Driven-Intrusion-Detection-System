import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useLiveMessages } from "../app/live";
import { useFetch } from "../app/useFetch";
import {
  Button, Card, DemoBadge, ErrorBox, SeverityBadge, SourceBadge, Spinner, StatusBadge,
  categoryLabel, fmtBytes, fmtTime, inputCls, statusLabel, td, th,
} from "../components/ui";
import { api } from "../services/api";
import { STATUSES, type AlertDetail, type AlertStatus } from "../types";

function EvidenceValue({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="text-slate-400">—</span>;
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x !== "object")) return <span className="font-mono text-xs">{v.join(", ") || "—"}</span>;
    if (v.every((x) => Array.isArray(x) && x.length === 2)) {
      // [value, count] pairs, e.g. top sources
      return <span className="font-mono text-xs">{(v as [unknown, unknown][]).map(([k, n]) => `${k} (${n})`).join(", ")}</span>;
    }
    return <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(v, null, 1)}</pre>;
  }
  if (typeof v === "object") {
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
        {Object.entries(v as Record<string, unknown>).map(([k, x]) => (
          <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd>{typeof x === "number" ? x.toLocaleString() : String(x)}</dd></div>
        ))}
      </dl>
    );
  }
  return <span className="font-mono text-xs">{typeof v === "number" ? v.toLocaleString() : String(v)}</span>;
}

export default function AlertDetailPage() {
  const { id } = useParams();
  const { canWrite } = useAuth();
  const { data: a, error, reload, setData } = useFetch(() => api.get<AlertDetail>(`/alerts/${id}`), [id]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useLiveMessages((m) => {
    if ((m.type === "alert" && m.alert.id === Number(id)) || m.type === "resync") reload();
  });

  async function setStatus(status: AlertStatus) {
    if (!a) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.patch(`/alerts/${a.id}`, { status });
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function addNote(e: FormEvent) {
    e.preventDefault();
    if (!a || !note.trim()) return;
    setBusy(true);
    try {
      const n = await api.post<AlertDetail["notes"][number]>(`/alerts/${a.id}/notes`, { note });
      setData({ ...a, notes: [...a.notes, n] });
      setNote("");
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!a) return error ? <ErrorBox error={error} /> : <div className="flex justify-center py-20"><Spinner /></div>;
  const ev = a.evidence_json;

  return (
    <>
      <Link to="/threats" className="text-sm text-teal-700 hover:underline dark:text-teal-400">← Threat center</Link>
      <div className="mb-5 mt-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={a.severity} />
            <StatusBadge status={a.status} />
            <SourceBadge source={a.detection_source} />
            {a.is_demo && <DemoBadge />}
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{a.title}</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Alert #{a.id} · <span className="capitalize">{categoryLabel(a.category)}</span> · {a.device_name} · seen {a.occurrence_count}×
          </p>
        </div>
        {canWrite && (
          <div className="flex flex-wrap gap-2">
            {STATUSES.filter((s) => s !== a.status).map((s) => (
              <Button key={s} size="sm" disabled={busy} onClick={() => setStatus(s)}
                variant={s === "resolved" ? "primary" : "secondary"}>
                Mark {statusLabel(s)}
              </Button>
            ))}
          </div>
        )}
      </div>
      <ErrorBox error={actionError} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Why this was flagged">
            <dl className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {Object.entries(ev).filter(([k]) => k !== "top_event_features").map(([k, v]) => (
                <div key={k} className="grid grid-cols-3 gap-3 py-1.5">
                  <dt className="text-slate-500">{k.replace(/_/g, " ")}</dt>
                  <dd className="col-span-2 break-words"><EvidenceValue v={v} /></dd>
                </div>
              ))}
            </dl>
          </Card>
          {"top_event_features" in ev && (
            <Card title="Feature values of the highest-scoring flow">
              <EvidenceValue v={ev.top_event_features} />
              <p className="mt-2 text-xs text-slate-500">These are the inputs the model saw. Feature importances (ML analytics page) are global and approximate, not a per-alert explanation.</p>
            </Card>
          )}
          <Card title={`Related flows (${a.related_events.length})`}>
            {a.related_events.length ? (
              <div className="-mx-4 overflow-x-auto">
                <table className="w-full min-w-[640px] text-xs tabular">
                  <thead className="border-b border-slate-100 dark:border-slate-800">
                    <tr><th className={th}>Time</th><th className={th}>Flow</th><th className={th}>State</th><th className={th}>Bytes</th><th className={th}>Model</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono dark:divide-slate-800">
                    {a.related_events.map((e) => (
                      <tr key={e.id}>
                        <td className={td + " whitespace-nowrap font-sans"}>{fmtTime(e.event_time, true)}</td>
                        <td className={td}>{e.protocol} {e.src_ip}:{e.src_port} → {e.dst_ip}:{e.dst_port}</td>
                        <td className={td}>{e.conn_state ?? e.dns_rcode ?? "—"}</td>
                        <td className={td}>{e.bytes_in == null ? "—" : fmtBytes((e.bytes_in ?? 0) + (e.bytes_out ?? 0))}</td>
                        <td className={td}>{e.ml_label ? `${e.ml_label} ${e.ml_score?.toFixed(2)}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-sm text-slate-500">Raw flows for this alert may have been removed by the retention policy.</p>}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Details">
            <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
              <dt className="text-slate-500">First seen</dt><dd>{fmtTime(a.first_seen_at, true)}</dd>
              <dt className="text-slate-500">Last seen</dt><dd>{fmtTime(a.last_seen_at, true)}</dd>
              <dt className="text-slate-500">Rule</dt><dd className="font-mono text-xs">{a.rule_id ?? "—"}</dd>
              <dt className="text-slate-500">Model</dt><dd className="break-all font-mono text-xs">{a.model_version ?? "—"}</dd>
              {a.score != null && (<><dt className="text-slate-500">Model score</dt><dd title={a.score_meaning ?? ""}>{a.score.toFixed(3)}*</dd></>)}
            </dl>
            {a.score != null && <p className="mt-2 text-xs text-slate-500">* {a.score_meaning}</p>}
          </Card>
          <Card title="Suggested investigation">
            <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{a.recommendation}</p>
            <p className="mt-2 text-xs text-slate-500">Indicators can have benign causes; see the rule documentation on the ML analytics page.</p>
          </Card>
          <Card title={`Investigation notes (${a.notes.length})`}>
            <ul className="space-y-3">
              {a.notes.map((n) => (
                <li key={n.id} className="text-sm">
                  <div className="text-xs text-slate-500">{n.author_email} · {fmtTime(n.created_at)}</div>
                  <p className="whitespace-pre-wrap">{n.note}</p>
                </li>
              ))}
            </ul>
            {canWrite && (
              <form onSubmit={addNote} className="mt-3 space-y-2">
                <textarea className={inputCls} rows={3} maxLength={5000} placeholder="Add a note…" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button size="sm" variant="primary" disabled={busy || !note.trim()}>Add note</Button>
              </form>
            )}
          </Card>
          <Card title="Audit trail">
            {a.audit_trail.length ? (
              <ol className="space-y-2 text-xs">
                {a.audit_trail.map((e) => (
                  <li key={e.id}>
                    <span className="text-slate-500">{fmtTime(e.created_at, true)}</span> · {e.actor_email ?? "system"} · {e.action}
                    {e.action === "alert.status_changed" && <> ({String(e.metadata_json.from)} → {String(e.metadata_json.to)})</>}
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-slate-500">No actions yet.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}
