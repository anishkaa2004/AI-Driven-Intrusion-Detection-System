import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useFallbackPolling, useLiveMessages } from "../app/live";
import { useFetch } from "../app/useFetch";
import AlertTable from "../components/AlertTable";
import { HBars, TrafficChart } from "../components/charts";
import { Card, Empty, ErrorBox, PageHeader, SEV_COLOR, Spinner, Stat, categoryLabel, cx, fmtNum } from "../components/ui";
import { api } from "../services/api";
import { SEVERITIES, type Summary } from "../types";

const WINDOWS = [
  { h: 1, label: "1h" },
  { h: 24, label: "24h" },
  { h: 168, label: "7d" },
];

export default function DashboardPage() {
  const [hours, setHours] = useState(24);
  const { data, error, reload } = useFetch(() => api.get<Summary>("/dashboard/summary", { hours }), [hours]);
  const pending = useRef<number | undefined>(undefined);

  // Coalesce bursts of live messages into one refresh.
  useLiveMessages((m) => {
    if (m.type === "pong") return;
    window.clearTimeout(pending.current);
    pending.current = window.setTimeout(reload, m.type === "resync" ? 0 : 1500);
  });
  useFallbackPolling(reload);

  const windowPicker = (
    <div className="inline-flex rounded-lg border border-slate-300 p-0.5 dark:border-slate-700">
      {WINDOWS.map((w) => (
        <button key={w.h} onClick={() => setHours(w.h)}
          className={cx("rounded-md px-3 py-1 text-xs font-medium",
            hours === w.h ? "bg-teal-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>
          {w.label}
        </button>
      ))}
    </div>
  );

  if (!data) {
    return (
      <>
        <PageHeader title="Dashboard" actions={windowPicker} />
        {error ? <ErrorBox error={error} /> : <div className="flex justify-center py-20"><Spinner /></div>}
      </>
    );
  }

  const d = data;
  const totalAlerts = SEVERITIES.reduce((n, s) => n + d.alerts_by_severity[s], 0);
  const noDevices = d.devices.total === 0;

  return (
    <>
      <PageHeader title="Dashboard" subtitle={`Last ${WINDOWS.find((w) => w.h === hours)?.label ?? hours + "h"} across your authorized devices`} actions={windowPicker} />
      <ErrorBox error={error} />
      {noDevices && (
        <Card className="mb-5">
          <Empty title="No devices enrolled yet">
            Enroll an authorized device on the <Link className="text-teal-700 underline dark:text-teal-400" to="/devices">Devices</Link> page,
            or run <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">python scripts/seed_demo_data.py</code> and the replay tool for demo data.
          </Empty>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Devices reporting" value={`${d.devices.reporting} / ${d.devices.total}`}
          hint={d.devices.stale + d.devices.offline > 0 ? `${d.devices.stale} stale · ${d.devices.offline} not reporting` : "All enrolled devices reporting"}
          tone={d.devices.offline + d.devices.stale > 0 ? "warn" : "ok"} />
        <Stat label="Flows processed" value={fmtNum(d.events)} hint="in selected window" />
        <Stat label="Alerts" value={fmtNum(totalAlerts)} hint="active in selected window" />
        <Stat label="Open alerts" value={fmtNum(d.open_alerts)} hint="new / acknowledged / investigating" tone={d.open_alerts ? "bad" : undefined} />
        <Stat label="Detection engine" value={d.health.model_loaded ? "Rules + ML" : "Rules only"}
          hint={d.health.model_version ?? d.health.model_error ?? ""} tone={d.health.model_loaded ? "ok" : "warn"} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Traffic and alerts over time" className="lg:col-span-2">
          {d.events === 0 && totalAlerts === 0
            ? <Empty title="No flows received in this period">Data appears here when an agent or the replay tool sends telemetry.</Empty>
            : <TrafficChart data={d.series} hours={hours} />}
        </Card>
        <Card title="Alerts by severity">
          {totalAlerts === 0
            ? <Empty title="No alerts observed during this period">This does not mean devices are safe — only that no rule or model fired.</Empty>
            : <HBars rows={SEVERITIES.map((s) => ({ label: s, value: d.alerts_by_severity[s], color: SEV_COLOR[s] }))} />}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Recent alerts" className="lg:col-span-2" actions={<Link to="/threats" className="text-xs text-teal-700 hover:underline dark:text-teal-400">Threat center →</Link>}>
          {d.recent_alerts.length ? <AlertTable alerts={d.recent_alerts} compact /> : <Empty title="No alerts yet" />}
        </Card>
        <div className="space-y-4">
          <Card title="Categories">
            <HBars rows={Object.entries(d.alerts_by_category).map(([k, v]) => ({ label: categoryLabel(k), value: v }))} color="#6366f1" />
          </Card>
          <Card title="Detection source">
            <HBars rows={Object.entries(d.alerts_by_source).map(([k, v]) => ({ label: k === "combined" ? "rule + ML" : k, value: v }))} color="#0ea5e9" />
          </Card>
          <Card title="Protocols">
            <HBars rows={Object.entries(d.protocols).map(([k, v]) => ({ label: k, value: v }))} />
          </Card>
        </div>
      </div>
    </>
  );
}
