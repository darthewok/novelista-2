"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = "idle" | "checking" | "ok" | "warn" | "error";

/** Tiny footer banner that pings Ollama once on mount and warns if unreachable.
 * Prevents the confusing "why is nothing happening?" state when the backend
 * is up but Ollama isn't.
 */
export function SettingsTestBanner() {
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      setStatus("checking");
      try {
        const r = await api.testConnection();
        if (!alive) return;
        if (r.model_present) {
          setStatus("ok");
          setMessage(`Connected · ${r.configured_model}`);
        } else {
          setStatus("warn");
          setMessage(`Ollama reachable but "${r.configured_model}" isn't pulled. Run: ollama pull ${r.configured_model}`);
        }
      } catch (e) {
        if (!alive) return;
        setStatus("error");
        setMessage((e as Error).message);
      }
    })();
    return () => { alive = false; };
  }, []);

  if (dismissed || status === "idle" || status === "checking" || status === "ok") return null;

  const color = status === "error" ? "bg-red-950/80 border-red-900 text-red-200"
                                   : "bg-amber-950/80 border-amber-900 text-amber-200";
  return (
    <div className={`fixed bottom-4 right-4 left-4 md:left-auto md:max-w-md z-30 border rounded-lg px-4 py-3 backdrop-blur ${color}`}>
      <div className="flex items-start justify-between gap-3 text-sm">
        <div>{message}</div>
        <button className="text-xs opacity-70 hover:opacity-100" onClick={() => setDismissed(true)}>dismiss</button>
      </div>
    </div>
  );
}
