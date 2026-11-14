import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useFallbackPolling, useLiveMessages } from "../app/live";
import { useFetch } from "../app/useFetch";
import { BytesChart, HBars, TrafficChart } from "../components/charts";
import {
  Button, Card, DemoBadge, Empty, ErrorBox, HealthBadge, PageHeader, Spinner, Stat,
  ago, fmtBytes, fmtNum, fmtTime, maskIp, selectInline, td, th,
} from "../components/ui";
import { api } from "../services/api";
import type { Device, FlowEvent } from "../types";

interface Traffic {
  device: Device;
  bucket_s: number;
  series: { t: string; flows: number; bytes_in: number; bytes_out: number }[];
  protocols: { protocol: string; flows: number }[];
  recent_flows: FlowEvent[];
  interface: { t: string; bytes_sent: number | null; bytes_recv: number | null; interval_s: number | null }[];
  agent: { received_at: string; cpu_percent: number | null; memory_mb: number | null; collector_status: string | null; queued_events: number | null } | null;
}

export default function LivePage() {
  const { canWrite } = useAuth();
  const [params, setParams] = useSearchParams();
  const devices = useFetch(() => api.get<Device[]>("/devices"), []);
  const active = (devices.data ?? []).filter((d) => d.status !== "pending");
  const selected = Number(params.get("device")) || active[0]?.id;
  const [minutes, setMinutes] = useState(60);
  const [reveal, setReveal] = useState(false);
  const traffic = useFetch(
    () => (selected ? api.get<Traffic>(`/devices/${selected}/traffic`, { minutes }) : Promise.resolve(null)),
    [selected, minutes],
  );
  const timer = useRef<number | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  useLiveMessages((m) => {
    if (m.type === "resync" || ((m.type === "events" || m.type === "device") &&
        (m.type === "events" ? m.device_id : m.device.id) === selected)) {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(traffic.reload, 1000);
    }
  });
  useFallbackPolling(traffic.reload, 15_000);

  // Re-evaluate "x seconds ago" labels and staleness even without new data.
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 5000);
    return () => window.clearInterval(id);
  }, []);

  async function togglePause(d: Device) {
    setBusy(true);
    try {
      await api.patch(`/devices/${d.id}`, { monitoring_paused: !d.monitoring_paused });
      await traffic.reload();
    } finally {
      setBusy(false);
    }
  }

  if (devices.loading && !devices.data) return <div className="flex justify-center py-20"><Spinner /></div>;
  if (!active.length) {
    return (
      <>
        <PageHeader title="Live monitoring" />
        <Card><Empty title="No enrolled devices">Enroll a device on the <Link to="/devices" className="text-teal-700 underline">Devices</Link> page first.</Empty></Card>
      </>
    );
  }

  const t = traffic.data;
  const dev = t?.device;
  const flows = t?.series.reduce((n, s) => n + s.flows, 0) ?? 0;
  const bytes = t?.series.reduce((n, s) => n + s.bytes_in + s.bytes_out, 0) ?? 0;
  const ifaceSeries = (t?.interface ?? []).map((h) => ({ t: h.t, bytes_in: h.bytes_recv ?? 0, bytes_out: h.bytes_sent ?? 0 }));
  const stale = dev && (dev.health === "stale" || dev.health === "offline");

  return (
    <>
      <PageHeader
        title="Live monitoring"
        subtitle="Flow metadata and agent health for one device"
        actions={
          <>
            <select className={selectInline} value={selected} onChange={(e) => setParams({ device: e.target.value })} aria-label="Device">
              {active.map((d) => <option key={d.id} value={d.id}>{d.display_name}{d.status === "revoked" ? " (revoked)" : ""}</option>)}
            </select>
            <select className={selectInline} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} aria-label="Window">
              <option value={15}>15 min</option>
              <option value={60}>1 hour</option>
              <option value={360}>6 hours</option>
              <option value={1440}>24 hours</option>
            </select>
          </>
        }
      />
      <ErrorBox error={traffic.error} />
      {dev && (
        <>
          {stale && (
            <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              This device has not reported since {fmtTime(dev.last_seen_at, true)} — data below may be out of date.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Status</div>
              <div className="mt-2"><HealthBadge health={dev.health} /></div>
              <div className="mt-1 text-xs text-slate-500">Last report {ago(dev.last_seen_at)}</div>
            </div>
            <Stat label="Flows" value={fmtNum(flows)} hint={`last ${minutes} min`} />
            <Stat label="Flow volume" value={fmtBytes(bytes)} hint="where counters were collected" />
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Collection</div>
              <div className="mt-1 text-sm font-medium">{dev.monitoring_paused ? "Paused" : dev.status === "revoked" ? "Revoked" : "Active"}</div>
              {canWrite && dev.status === "active" && (
                <Button size="sm" className="mt-1.5" disabled={busy} onClick={() => togglePause(dev)}>
                  {dev.monitoring_paused ? "Resume collection" : "Pause collection"}
                </Button>
              )}
              {dev.monitoring_paused && <div className="mt-1 text-xs text-slate-500">The agent stops collecting at its next heartbeat; heartbeats continue.</div>}
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Flows over time" className="lg:col-span-2">
              {flows ? <TrafficChart data={t.series} hours={minutes / 60} height={220} /> : <Empty title="No flows in this window" />}
            </Card>
            <Card title="Protocol distribution">
              <HBars rows={t.protocols.map((p) => ({ label: p.protocol, value: p.flows }))} />
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Interface throughput (from agent heartbeats)" className="lg:col-span-2">
              {ifaceSeries.length ? <BytesChart data={ifaceSeries} /> : <Empty title="No heartbeats in this window">Interface counters are reported by the live agent, not by replay.</Empty>}
            </Card>
            <Card title="Agent health">
              {t.agent ? (
                <dl className="grid grid-cols-2 gap-y-2 text-sm">
                  <dt className="text-slate-500">Heartbeat</dt><dd>{ago(t.agent.received_at)}</dd>
                  <dt className="text-slate-500">Agent CPU</dt><dd>{t.agent.cpu_percent ?? "—"}%</dd>
                  <dt className="text-slate-500">Agent memory</dt><dd>{t.agent.memory_mb ?? "—"} MB</dd>
                  <dt className="text-slate-500">Send queue</dt><dd>{t.agent.queued_events ?? 0}</dd>
                  <dt className="text-slate-500">Version</dt><dd>{dev.agent_version ?? "—"}</dd>
                  <dt className="col-span-2 text-slate-500">Collector</dt>
                  <dd className="col-span-2 text-xs">{t.agent.collector_status ?? dev.last_collector ?? "—"}</dd>
                </dl>
              ) : <Empty title="No agent heartbeat">{dev.last_collector === "replay" ? "This device receives replayed demo data." : "Start the agent on this device."}</Empty>}
            </Card>
          </div>

          <Card title="Recent flows" className="mt-4" actions={
            <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
              <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} /> Show full IP addresses
            </label>
          }>
            {t.recent_flows.length ? (
              <div className="-mx-4 overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm tabular">
                  <thead className="border-b border-slate-100 dark:border-slate-800">
                    <tr>
                      <th className={th}>Time</th><th className={th}>Proto</th><th className={th}>Source</th>
                      <th className={th}>Destination</th><th className={th}>State</th><th className={th}>Pkts in/out</th>
                      <th className={th}>Bytes in/out</th><th className={th}>Model label</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-xs dark:divide-slate-800">
                    {t.recent_flows.map((f) => (
                      <tr key={f.id}>
                        <td className={td + " whitespace-nowrap font-sans"}>{fmtTime(f.event_time, true)} {f.source === "replay" && <DemoBadge />}</td>
                        <td className={td}>{f.protocol}</td>
                        <td className={td}>{maskIp(f.src_ip, reveal)}:{f.src_port ?? "—"}</td>
                        <td className={td}>{maskIp(f.dst_ip, reveal)}:{f.dst_port ?? "—"}</td>
                        <td className={td}>{f.conn_state ?? f.dns_rcode ?? "—"}</td>
                        <td className={td}>{f.packets_in ?? "—"}/{f.packets_out ?? "—"}</td>
                        <td className={td}>{f.bytes_in == null ? "—" : `${fmtBytes(f.bytes_in)} / ${fmtBytes(f.bytes_out)}`}</td>
                        <td className={td + " font-sans"}>
                          {f.ml_label ? <span className={f.ml_label === "BENIGN" ? "text-slate-500" : "font-medium text-red-600 dark:text-red-400"}>
                            {f.ml_label} <span className="text-slate-400">{f.ml_score?.toFixed(2)}</span></span>
                            : <span className="text-slate-400" title="Model is not applied when packet/byte counters were not collected">not scored</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Empty title="No flows recorded yet" />}
          </Card>
        </>
      )}
    </>
  );
}
