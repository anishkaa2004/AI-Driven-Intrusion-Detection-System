import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useFallbackPolling, useLiveMessages } from "../app/live";
import { useFetch } from "../app/useFetch";
import { Button, Card, Empty, ErrorBox, Field, HealthBadge, PageHeader, Spinner, ago, fmtNum, fmtTime, inputCls, td, th } from "../components/ui";
import { api } from "../services/api";
import type { Device } from "../types";

interface Enrollment {
  device_id: number;
  enrollment_code: string;
  expires_at: string;
}

export default function DevicesPage() {
  const { canWrite, isAdmin } = useAuth();
  const { data, error, reload, setData } = useFetch(() => api.get<Device[]>("/devices"), []);
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("");
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useLiveMessages((m) => {
    if (m.type === "device" && data) {
      const found = data.some((d) => d.id === m.device.id);
      if (found) setData(data.map((d) => (d.id === m.device.id ? { ...d, ...m.device, events_24h: d.events_24h, open_alerts: d.open_alerts } : d)));
      else reload();
    } else if (m.type === "resync") reload();
  });
  useFallbackPolling(reload);

  async function enroll(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      setEnrollment(await api.post<Enrollment>("/devices/enroll", { display_name: name, platform: platform || null }));
      setName("");
      setPlatform("");
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(d: Device) {
    if (!confirm(`Revoke "${d.display_name}"? Its agent credential stops working immediately.`)) return;
    try {
      await api.post(`/devices/${d.id}/revoke`);
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function reissue(d: Device) {
    try {
      setEnrollment(await api.post<Enrollment>(`/devices/${d.id}/enrollment-code`));
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  const notReporting = (data ?? []).filter((d) => d.health === "stale" || d.health === "offline");
  const server = `${location.protocol}//${location.hostname}:8000`;

  return (
    <>
      <PageHeader title="Devices" subtitle="Enroll, monitor and revoke authorized monitoring agents" />
      <ErrorBox error={error ?? actionError} />
      {notReporting.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {notReporting.map((d) => d.display_name).join(", ")} {notReporting.length === 1 ? "has" : "have"} stopped reporting. Their data may be stale.
        </div>
      )}

      {canWrite && (
        <Card title="Enroll a device" className="mb-4">
          <form onSubmit={enroll} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label="Display name"><input className={inputCls} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. My laptop" /></Field>
            <Field label="Platform (optional)"><input className={inputCls} maxLength={50} value={platform} onChange={(e) => setPlatform(e.target.value)} placeholder="macOS, Windows, Linux…" /></Field>
            <Button variant="primary" disabled={busy || !name.trim()}>Create enrollment code</Button>
          </form>
          <p className="mt-2 text-xs text-slate-500">Only enroll devices you own or are explicitly authorized to monitor. The code is single-use and expires in 15 minutes.</p>
          {enrollment && (
            <div className="mt-4 rounded-lg border border-teal-300 bg-teal-50 p-4 dark:border-teal-800 dark:bg-teal-950/40">
              <div className="text-sm font-medium">Enrollment code for device #{enrollment.device_id}</div>
              <div className="my-2 font-mono text-2xl tracking-widest">{enrollment.enrollment_code}</div>
              <div className="text-xs text-slate-600 dark:text-slate-300">Expires {fmtTime(enrollment.expires_at, true)}. It will not be shown again. On the device, from the <code>agent/</code> folder, run:</div>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-2 text-xs text-slate-100">python -m agent register --server {server} --code {enrollment.enrollment_code}{"\n"}python -m agent run</pre>
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setEnrollment(null)}>Done</Button>
            </div>
          )}
        </Card>
      )}

      <Card title="Enrolled devices">
        {!data ? <div className="flex justify-center py-8"><Spinner /></div> : data.length === 0 ? (
          <Empty title="No devices yet">Create an enrollment code above, then register the agent on the device.</Empty>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className={th}>Device</th><th className={th}>Status</th><th className={th}>Last seen</th>
                  <th className={th}>Agent</th><th className={th}>Flows 24h</th><th className={th}>Open alerts</th>
                  {isAdmin && <th className={th}>Owner</th>}<th className={th}>Enrolled</th><th className={th} />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.map((d) => (
                  <tr key={d.id} className={d.status === "revoked" ? "opacity-60" : ""}>
                    <td className={td}>
                      <Link to={`/live?device=${d.id}`} className="font-medium hover:text-teal-700 hover:underline">{d.display_name}</Link>
                      <div className="text-xs text-slate-500">{[d.hostname, d.platform].filter(Boolean).join(" · ") || "—"}</div>
                    </td>
                    <td className={td}>
                      <HealthBadge health={d.health} />
                      {d.monitoring_paused && <div className="text-xs text-slate-500">collection paused</div>}
                    </td>
                    <td className={td + " text-slate-600 dark:text-slate-300"} title={fmtTime(d.last_seen_at, true)}>{ago(d.last_seen_at)}</td>
                    <td className={td + " text-xs text-slate-500"}>{d.agent_version ?? "—"}<div>{d.last_collector}</div></td>
                    <td className={td + " tabular"}>{fmtNum(d.events_24h)}</td>
                    <td className={td + " tabular"}>{d.open_alerts ? <Link className="font-medium text-red-600 hover:underline" to={`/threats`}>{d.open_alerts}</Link> : 0}</td>
                    {isAdmin && <td className={td + " text-xs text-slate-500"}>{d.owner_email}</td>}
                    <td className={td + " text-xs text-slate-500"}>{fmtTime(d.enrolled_at ?? d.created_at)}</td>
                    <td className={td + " text-right"}>
                      {canWrite && d.status === "pending" && <Button size="sm" variant="ghost" onClick={() => reissue(d)}>New code</Button>}
                      {canWrite && d.status !== "revoked" && <Button size="sm" variant="ghost" className="text-red-600 dark:text-red-400" onClick={() => revoke(d)}>Revoke</Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
