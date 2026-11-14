import { useRef, useState } from "react";
import { useFallbackPolling, useLiveMessages } from "../app/live";
import { useFetch } from "../app/useFetch";
import AlertTable from "../components/AlertTable";
import { Button, Card, Empty, ErrorBox, PageHeader, Spinner, categoryLabel, cx, inputCls, statusLabel } from "../components/ui";
import { api, downloadCsv } from "../services/api";
import { OPEN_STATUSES, SEVERITIES, STATUSES, type Alert, type Device, type Page } from "../types";

function Chips<T extends string>({ options, value, onChange, label }: {
  options: T[]; value: T[]; onChange: (v: T[]) => void; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button key={o} type="button" aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}
            className={cx("rounded-full border px-2.5 py-0.5 text-xs capitalize",
              on ? "border-teal-600 bg-teal-600 text-white"
                : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800")}>
            {statusLabel(o)}
          </button>
        );
      })}
    </div>
  );
}

export default function AlertsPage({ mode }: { mode: "threats" | "history" }) {
  const isHistory = mode === "history";
  return <AlertsView key={mode} isHistory={isHistory} />;
}

function AlertsView({ isHistory }: { isHistory: boolean }) {
  const [statuses, setStatuses] = useState<string[]>(isHistory ? [] : OPEN_STATUSES);
  const [severities, setSeverities] = useState<string[]>([]);
  const [category, setCategory] = useState("");
  const [source, setSource] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [includeDemo, setIncludeDemo] = useState(true);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const pageSize = 25;

  const params = {
    status: statuses.join(","), severity: severities.join(","), category, source,
    device_id: deviceId, include_demo: includeDemo,
    start: start ? new Date(start).toISOString() : "", end: end ? new Date(end).toISOString() : "",
  };
  const key = JSON.stringify(params);
  const alerts = useFetch(() => api.get<Page<Alert>>("/alerts", { ...params, page, page_size: pageSize }), [key, page]);
  const devices = useFetch(() => api.get<Device[]>("/devices"), []);
  const categories = useFetch(() => api.get<string[]>("/alerts/categories"), []);
  const timer = useRef<number | undefined>(undefined);

  useLiveMessages((m) => {
    if (m.type === "alert" || m.type === "resync") {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => { alerts.reload(); categories.reload(); }, 1000);
    }
  });
  useFallbackPolling(alerts.reload);

  const set = <T,>(fn: (v: T) => void) => (v: T) => { fn(v); setPage(1); };
  const totalPages = Math.max(1, Math.ceil((alerts.data?.total ?? 0) / pageSize));

  async function exportCsv() {
    setExporting(true);
    try {
      await downloadCsv("/reports/alerts.csv", params);
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <PageHeader
        title={isHistory ? "Incident history" : "Threat center"}
        subtitle={isHistory ? "Search, filter and export all alerts you are authorized to see"
          : "Open alerts that need triage. Each alert shows the evidence behind it."}
        actions={<Button onClick={exportCsv} disabled={exporting}>{exporting ? "Exporting…" : "Export CSV"}</Button>}
      />
      <Card className="mb-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">Status</div>
              <Chips label="Status" options={STATUSES} value={statuses} onChange={set(setStatuses)} />
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">Severity</div>
              <Chips label="Severity" options={SEVERITIES} value={severities} onChange={set(setSeverities)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <select className={inputCls} value={deviceId} onChange={(e) => set(setDeviceId)(e.target.value)} aria-label="Device">
              <option value="">All devices</option>
              {devices.data?.map((d) => <option key={d.id} value={d.id}>{d.display_name}</option>)}
            </select>
            <select className={inputCls} value={category} onChange={(e) => set(setCategory)(e.target.value)} aria-label="Category">
              <option value="">All categories</option>
              {categories.data?.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
            </select>
            <select className={inputCls} value={source} onChange={(e) => set(setSource)(e.target.value)} aria-label="Detection source">
              <option value="">Any source</option>
              <option value="rule">Rule</option>
              <option value="ml">ML model</option>
              <option value="combined">Rule + ML</option>
            </select>
            {isHistory && (
              <>
                <input type="datetime-local" className={inputCls} value={start} onChange={(e) => set(setStart)(e.target.value)} aria-label="From" />
                <input type="datetime-local" className={inputCls} value={end} onChange={(e) => set(setEnd)(e.target.value)} aria-label="To" />
              </>
            )}
            <label className="col-span-2 flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 sm:col-span-1">
              <input type="checkbox" checked={includeDemo} onChange={(e) => set(setIncludeDemo)(e.target.checked)} />
              Include demo data
            </label>
          </div>
        </div>
      </Card>
      <ErrorBox error={alerts.error} />
      <Card title={alerts.data ? `${alerts.data.total.toLocaleString()} alert${alerts.data.total === 1 ? "" : "s"}` : "Alerts"}
        actions={alerts.loading && <Spinner />}>
        {alerts.data && alerts.data.items.length > 0 ? (
          <>
            <AlertTable alerts={alerts.data.items} />
            <div className="mt-3 flex items-center justify-between text-sm text-slate-500">
              <span>Page {page} of {totalPages}</span>
              <div className="flex gap-2">
                <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          </>
        ) : alerts.data ? (
          <Empty title={isHistory ? "No alerts match these filters" : "No open alerts"}>
            {!isHistory && "No rule or model has flagged activity that still needs triage. This is not a guarantee that no attack occurred."}
          </Empty>
        ) : <div className="flex justify-center py-10"><Spinner /></div>}
      </Card>
    </>
  );
}
