import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../app/auth";
import { api } from "../services/api";
import { Button, ErrorBox, Field, inputCls } from "../components/ui";

export default function LoginPage() {
  const { login } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [cfg, setCfg] = useState<{ registration_open: boolean; has_users: boolean } | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<{ registration_open: boolean; has_users: boolean }>("/auth/config").then((c) => {
      setCfg(c);
      if (!c.has_users) setMode("register");
    }).catch(() => setError("Cannot reach the AI-IDS backend. Is it running on port 8000?"));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") await api.post("/auth/register", { email, password });
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <img src="/shield.svg" alt="" className="h-10 w-10" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">AI-IDS</h1>
            <p className="text-sm text-slate-500">Network intrusion detection &amp; threat monitoring</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-base font-semibold">{mode === "login" ? "Sign in" : cfg?.has_users ? "Create account" : "Create the administrator account"}</h2>
          {cfg && !cfg.has_users && (
            <p className="text-sm text-slate-500">No accounts exist yet. The first account becomes the administrator.</p>
          )}
          <ErrorBox error={error} />
          <Field label="Email">
            <input className={inputCls} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
            <input className={inputCls} type="password" required minLength={mode === "register" ? 10 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button variant="primary" className="w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
          {cfg?.registration_open && cfg.has_users && (
            <button type="button" className="w-full text-center text-sm text-teal-700 hover:underline dark:text-teal-400"
              onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
              {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
            </button>
          )}
        </form>
        <p className="mt-4 text-center text-xs text-slate-500">
          Monitor only devices you own or are explicitly authorized to monitor.
        </p>
      </div>
    </div>
  );
}
