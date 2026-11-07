import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAction } from "@/lib/useAction";
import { ErrorLine } from "@/components/ErrorLine";
import { api, type ConnectionTest, type Provider, type Settings, type Task } from "@/lib/api";

const PROVIDERS: Provider[] = ["anthropic", "openai", "openrouter", "lmstudio", "ollama"];
const TASKS: { key: Task; hint: string }[] = [
  { key: "outline", hint: "structure, run once" },
  { key: "draft", hint: "prose" },
  { key: "revise", hint: "prose" },
  { key: "editor", hint: "revision briefs" },
  { key: "foundation", hint: "world/characters" },
  { key: "voice", hint: "voice document and trials" },
  { key: "seed", hint: "story candidates" },
  { key: "summary", hint: "extraction, cheap" },
  { key: "canon", hint: "extraction, cheap" },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [form, setForm] = useState<Settings | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({}); // typed keys only; empty = unchanged
  const [saved, setSaved] = useState(false);
  const saveAct = useAction();
  const testQ = useQuery({ queryKey: ["connection-test"], queryFn: api.testConnection });
  const test: ConnectionTest | null = testQ.data ?? null;
  const testing = testQ.isFetching;
  const detected = test?.ok ? test.available_models : [];

  useEffect(() => { if (data) setForm(structuredClone(data)); }, [data]);
  // Prefill task models from the detected list when the current values do not belong to this provider.
  useEffect(() => {
    if (!form || detected.length === 0) return;
    const current = Object.values(form.models);
    if (current.every((m) => detected.includes(m))) return;
    setAllModels(detected[0]);
    // Persist the prefill so the connection banner reflects it without a manual Save.
    const models = Object.fromEntries(TASKS.map((t) => [t.key, detected[0]])) as Settings["models"];
    api.putSettings({ models }).then((next) => { qc.setQueryData(["settings"], next); testQ.refetch(); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detected.join("|")]);
  if (!form) return <div className="text-slate-400">Loading…</div>;

  const p = form.provider;
  const cfg = form.providers[p] ?? {};
  const setCfg = (patch: Partial<typeof cfg>) =>
    setForm({ ...form, providers: { ...form.providers, [p]: { ...cfg, ...patch } } });
  const setModel = (t: Task, v: string) => setForm({ ...form, models: { ...form.models, [t]: v } });
  const setQuality = (patch: Partial<Settings["quality"]>) => setForm({ ...form, quality: { ...form.quality, ...patch } });
  const preset = (m: string) => setForm({ ...form, models: { ...form.models, draft: m, revise: m, editor: m } });
  function setAllModels(m: string) {
    setForm((f) => f && { ...f, models: Object.fromEntries(TASKS.map((t) => [t.key, m])) as Settings["models"] });
  }

  async function runTest() {
    await testQ.refetch();
  }

  // Switching provider is saved at once so the connection test (and the model prefill) run against it.
  async function changeProvider(n: Provider) {
    setForm({ ...form!, provider: n });
    await saveAct.run(async () => {
      const next = await api.putSettings({ provider: n });
      qc.setQueryData(["settings"], next);
      setForm((f) => f && { ...next, models: f.models, quality: f.quality, providers: { ...next.providers, ...f.providers } });
    });
    await runTest();
  }

  async function save() {
    setSaved(false);
    await saveAct.run(async () => {
      const providers: Settings["providers"] = {};
      for (const [name, c] of Object.entries(form!.providers)) {
        const { api_key: _masked, ...rest } = c;
        providers[name] = keys[name] ? { ...rest, api_key: keys[name] } : rest;
      }
      const next = await api.putSettings({ provider: form!.provider, providers, models: form!.models, quality: form!.quality });
      setKeys({});
      qc.setQueryData(["settings"], next);
      setSaved(true);
      await runTest();
    });
  }

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-slate-400 mt-1">Choose a provider, add its key, and pick a model per task.</p>
      </div>

      <section className="space-y-4">
        <div>
          <label className="label" htmlFor="provider">Provider</label>
          <select id="provider" className="select" value={p} onChange={(e) => changeProvider(e.target.value as Provider)}>
            {PROVIDERS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="api-key">API key</label>
          <input id="api-key" className="input" type="password" autoComplete="off" value={keys[p] ?? ""}
                 placeholder={cfg.api_key || "not set"}
                 onChange={(e) => setKeys({ ...keys, [p]: e.target.value })} />
          <p className="text-xs text-slate-500 mt-1">Leave as is to keep the current key.</p>
        </div>
        {p !== "anthropic" && (
          <div>
            <label className="label" htmlFor="base-url">Base URL</label>
            <input id="base-url" className="input" value={cfg.base_url ?? ""} onChange={(e) => setCfg({ base_url: e.target.value })} />
          </div>
        )}
        {p === "ollama" && (
          <div>
            <label className="label" htmlFor="num-ctx">num_ctx</label>
            <input id="num-ctx" className="input" type="number" min={512} value={cfg.num_ctx ?? ""}
                   onChange={(e) => setCfg({ num_ctx: e.target.value ? Number(e.target.value) : undefined })} />
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Models</h2>
          {detected.length > 1 && (
            <label className="text-sm text-slate-400 flex items-center gap-2">
              Set all tasks to
              <select aria-label="Set all tasks to a detected model" className="select text-sm" value=""
                      onChange={(e) => { if (e.target.value) setAllModels(e.target.value); }}>
                <option value="">{detected.length} detected…</option>
                {detected.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          )}
          {p === "anthropic" && (
            <div className="flex gap-2">
              <button type="button" className="btn-ghost text-sm" onClick={() => preset("claude-sonnet-5-5")}>Economy</button>
              <button type="button" className="btn-ghost text-sm" onClick={() => preset("claude-opus-5-5")}>Quality</button>
            </div>
          )}
        </div>
        <datalist id="detected-models">{detected.map((m) => <option key={m} value={m} />)}</datalist>
        <table className="w-full text-sm">
          <tbody>
            {TASKS.map((t) => (
              <tr key={t.key}>
                <td className="py-1 pr-3 w-28 capitalize">{t.key}</td>
                <td className="py-1 pr-3"><input aria-label={`${t.key} model`} className="input" list="detected-models" value={form.models[t.key] ?? ""}
                                                 onChange={(e) => setModel(t.key, e.target.value)} /></td>
                <td className="py-1 text-xs text-slate-500">{t.hint}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Quality</h2>
        <label htmlFor="auto-polish" className="flex items-center gap-2">
          <input id="auto-polish" type="checkbox" checked={form.quality.auto_polish}
                 onChange={(e) => setQuality({ auto_polish: e.target.checked })} />
          Auto-polish drafts
        </label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="max-polish-passes">Max polish passes (1–3)</label>
            <input id="max-polish-passes" className="input" type="number" min={1} max={3} value={form.quality.max_polish_passes}
                   onChange={(e) => setQuality({ max_polish_passes: Math.min(3, Math.max(1, Number(e.target.value) || 1)) })} />
          </div>
          <div>
            <label className="label" htmlFor="tells-threshold">Tells threshold</label>
            <input id="tells-threshold" className="input" type="number" min={0} value={form.quality.tells_threshold}
                   onChange={(e) => setQuality({ tells_threshold: Number(e.target.value) || 0 })} />
          </div>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button className="btn" onClick={save} disabled={saveAct.busy}>Save</button>
        <button className="btn-ghost" onClick={runTest} disabled={testing}>{testing ? "Testing…" : "Test connection"}</button>
        {saved && <span className="text-sm text-emerald-400">Saved</span>}
      </div>
      <ErrorLine error={saveAct.error} />

      <ErrorLine error={testQ.error ? String(testQ.error) : null} />
      {test && (
        <div className="card space-y-2 text-sm">
          {test.ok
            ? <div className="text-emerald-400">OK · {test.provider} · {test.available_models.length} model(s) available</div>
            : <div className="text-red-300">Failed: {test.error ?? "unknown error"}</div>}
          <ul className="grid grid-cols-3 gap-1">
            {Object.entries(test.models_present).map(([t, ok]) => (
              <li key={t} className={ok ? "text-emerald-400" : "text-red-400"}>{ok ? "✓" : "✗"} {t}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
