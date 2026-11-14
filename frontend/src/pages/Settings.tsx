import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../app/auth";
import { useFetch } from "../app/useFetch";
import { Button, Card, ErrorBox, Field, PageHeader, Spinner, fmtTime, inputCls, selectInline, td, th } from "../components/ui";
import { api } from "../services/api";
import { SEVERITIES, type Role, type RuleDoc, type User } from "../types";

type Cfg = Record<string, number | boolean | string>;
interface SettingsData {
  rules: Record<string, Cfg>;
  ml: Cfg;
  retention: Cfg;
  rule_docs: RuleDoc[];
  editable: boolean;
}

function ConfigForm({ title, value, onSave, editable, docs }: {
  title: string; value: Cfg; onSave: (v: Cfg) => Promise<void>; editable: boolean; docs?: string;
}) {
  const [draft, setDraft] = useState(value);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setDraft(value), [value]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await onSave(draft);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    }
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-slate-500">{title}</div>
          {docs && <div className="text-xs text-slate-500">{docs}</div>}
        </div>
        {editable && <Button size="sm" variant="primary">{saved ? "Saved ✓" : "Save"}</Button>}
      </div>
      <ErrorBox error={err} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(draft).map(([k, v]) => (
          <Field key={k} label={k.replace(/_/g, " ")}>
            {typeof v === "boolean" ? (
              <input type="checkbox" disabled={!editable} checked={v} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })} />
            ) : k === "severity" ? (
              <select className={inputCls} disabled={!editable} value={String(v)} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}>
                {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
              </select>
            ) : (
              <input className={inputCls} type="number" step="any" disabled={!editable} value={String(v)}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value === "" ? "" : Number(e.target.value) })} />
            )}
          </Field>
        ))}
      </div>
    </form>
  );
}

function Users() {
  const { user: me } = useAuth();
  const { data, error, reload } = useFetch(() => api.get<User[]>("/users"), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [err, setErr] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/users", { email, password, role });
      setEmail("");
      setPassword("");
      reload();
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    }
  }
  async function update(u: User, change: Partial<User>) {
    setErr(null);
    try {
      await api.patch(`/users/${u.id}`, change);
      reload();
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    }
  }

  return (
    <Card title="Users and roles" className="mt-4">
      <ErrorBox error={error ?? err} />
      <form onSubmit={create} className="mb-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
        <Field label="Email"><input className={inputCls} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Initial password"><input className={inputCls} type="password" minLength={10} required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <Field label="Role">
          <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="analyst">analyst</option><option value="viewer">viewer</option><option value="admin">admin</option>
          </select>
        </Field>
        <Button variant="primary">Add user</Button>
      </form>
      {!data ? <Spinner /> : (
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr><th className={th}>Email</th><th className={th}>Role</th><th className={th}>Active</th><th className={th}>Created</th></tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.map((u) => (
                <tr key={u.id}>
                  <td className={td}>{u.email}{u.id === me?.id && <span className="ml-1 text-xs text-slate-500">(you)</span>}</td>
                  <td className={td}>
                    <select className={selectInline + " py-1"} value={u.role} onChange={(e) => update(u, { role: e.target.value as Role })}>
                      <option>admin</option><option>analyst</option><option>viewer</option>
                    </select>
                  </td>
                  <td className={td}><input type="checkbox" checked={u.is_active} onChange={(e) => update(u, { is_active: e.target.checked })} /></td>
                  <td className={td + " text-xs text-slate-500"}>{fmtTime(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">Admins see all devices. Analysts manage their own devices and alerts. Viewers have read-only access to their own devices.</p>
    </Card>
  );
}

export default function SettingsPage() {
  const { isAdmin } = useAuth();
  const { data, error, reload } = useFetch(() => api.get<SettingsData>("/settings"), []);
  if (!data) return error ? <ErrorBox error={error} /> : <div className="flex justify-center py-20"><Spinner /></div>;
  const docs = Object.fromEntries(data.rule_docs.map((d) => [d.rule_id, d.name]));

  const saveRule = (id: string) => async (v: Cfg) => {
    await api.put("/settings/rules", { ...data.rules, [id]: v });
    await reload();
  };
  const save = (key: string) => async (v: Cfg) => {
    await api.put(`/settings/${key}`, v);
    await reload();
  };

  return (
    <>
      <PageHeader title="Settings" subtitle={data.editable ? "Changes take effect for the next telemetry batch and are recorded in the audit log." : "Read-only: only administrators can change settings."} />
      <Card title="Rule thresholds">
        <div className="space-y-3">
          {Object.entries(data.rules).map(([id, cfg]) => (
            <ConfigForm key={id} title={id} docs={docs[id]} value={cfg} editable={data.editable} onSave={saveRule(id)} />
          ))}
        </div>
      </Card>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="ML alerting">
          <ConfigForm title="ml" value={data.ml} editable={data.editable} onSave={save("ml")}
            docs="Alert when ≥ min events from one source get the same non-benign label with score ≥ min score." />
        </Card>
        <Card title="Data retention">
          <ConfigForm title="retention" value={data.retention} editable={data.editable} onSave={save("retention")}
            docs="Raw flows and heartbeats older than this are deleted hourly. Alerts and notes are kept." />
        </Card>
      </div>
      {isAdmin && <Users />}
    </>
  );
}
