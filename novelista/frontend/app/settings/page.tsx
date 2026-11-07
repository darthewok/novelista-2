"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [chapterCount, setChapterCount] = useState("");
  const [targetWords, setTargetWords] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setUrl(data.ollama_url);
      setModel(data.model);
      setChapterCount(data.default_chapter_count?.toString() ?? "");
      setTargetWords(data.default_target_words?.toString() ?? "");
    }
  }, [data]);

  async function save() {
    await api.putSettings({
      ollama_url: url,
      model,
      default_chapter_count: chapterCount ? Number(chapterCount) : null,
      default_target_words: targetWords ? Number(targetWords) : null,
    });
    qc.invalidateQueries({ queryKey: ["settings"] });
  }

  async function test() {
    setTesting(true); setTestResult(null); setTestError(null);
    try {
      const r = await api.testConnection();
      setTestResult(r.model_present
        ? `OK · ${r.available_models.length} model(s) available · "${r.configured_model}" is pulled.`
        : `Reached Ollama but "${r.configured_model}" is NOT pulled. Available: ${r.available_models.join(", ") || "(none)"}`);
    } catch (e) {
      setTestError((e as Error).message);
    } finally { setTesting(false); }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-slate-400 mt-1">Point Novelista at your Ollama server and choose a model.</p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="label">Ollama URL</label>
          <input className="input" value={url} onChange={(e) => setUrl(e.target.value)}
                 placeholder="http://localhost:11434" />
        </div>
        <div>
          <label className="label">Model</label>
          <input className="input" value={model} onChange={(e) => setModel(e.target.value)}
                 placeholder="qwen3.6:35b-a3b" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Default chapter count</label>
            <input className="input" type="number" min={1} value={chapterCount}
                   onChange={(e) => setChapterCount(e.target.value)} placeholder="auto" />
          </div>
          <div>
            <label className="label">Default target words</label>
            <input className="input" type="number" min={500} value={targetWords}
                   onChange={(e) => setTargetWords(e.target.value)} placeholder="auto" />
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <button className="btn" onClick={save}>Save</button>
        <button className="btn-ghost" onClick={test} disabled={testing}>
          {testing ? "Testing…" : "Test connection"}
        </button>
      </div>

      {testResult && <div className="card text-sm text-emerald-300">{testResult}</div>}
      {testError && <div className="card text-sm text-red-400">{testError}</div>}
    </div>
  );
}
