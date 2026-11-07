import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { subscribeJob } from "@/lib/sse";
import { api } from "@/lib/api";

export type JobStreamState = {
  text: string;
  running: boolean;
  status: "idle" | "starting" | "streaming" | "done" | "error" | "cancelled";
  startedAt: number | null;
  elapsedMs: number;
  wordCount: number;
  charCount: number;
  tokensPerSec: number;
  error: string | null;
  chapter: number | null;
  warnings: string[];
  brief: string | null;
  reconnected: boolean;
};

export type JobMeta = { bookId?: string; chapter?: number; kind?: string };
const storeKey = (bookId: string, chapter?: number) => `novelista.job.${bookId}.${chapter ?? "x"}`;
const ss = {
  get: (k: string) => { try { return sessionStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { sessionStorage.setItem(k, v); } catch {} },
  del: (k: string) => { try { sessionStorage.removeItem(k); } catch {} },
};

/** Single React hook that owns the streaming lifecycle for any generation job.
 *
 * Exposes rich progress metrics so UI can show a live pulse, elapsed clock,
 * word count, and characters/sec — even before the model emits the first token.
 */
export function useJobStream() {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<JobStreamState["status"]>("idle");
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [chapter, setChapter] = useState<number | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [brief, setBrief] = useState<string | null>(null);
  const [reconnected, setReconnected] = useState(false);
  const qc = useQueryClient();
  const unsubRef = useRef<(() => void) | null>(null);
  const tickRef = useRef<number | null>(null);

  // Tick elapsed clock while active so the UI updates even when tokens stall.
  useEffect(() => {
    if (status === "starting" || status === "streaming") {
      tickRef.current = window.setInterval(() => {
        if (startedAt) setElapsedMs(Date.now() - startedAt);
      }, 200);
      return () => { if (tickRef.current) window.clearInterval(tickRef.current); };
    }
    if (tickRef.current) window.clearInterval(tickRef.current);
  }, [status, startedAt]);

  const jobIdRef = useRef<string | null>(null);

  const stop = useCallback(() => {
    unsubRef.current?.();
    unsubRef.current = null;
  }, []);

  const cancel = useCallback(async () => {
    const jid = jobIdRef.current;
    if (!jid) return;
    try { await api.cancelJob(jid); } catch {}
  }, []);

  useEffect(() => () => stop(), [stop]);

  const attach = useCallback((jobId: string, meta: JobMeta = {}, isReconnect = false) => {
    stop();
    jobIdRef.current = jobId;
    if (!isReconnect) { setText(""); setBrief(null); }
    setWarnings([]);
    setReconnected(isReconnect);
    setError(null);
    setChapter(meta.chapter ?? null);
    setStatus("starting");
    const begin = Date.now();
    setStartedAt(begin);
    setElapsedMs(0);
    const key = meta.bookId ? storeKey(meta.bookId, meta.chapter) : null;
    if (key && !isReconnect) ss.set(key, JSON.stringify({ jobId, ...meta }));
    const refresh = (ch?: number) => {
      if (!meta.bookId) return;
      const b = meta.bookId, n = ch ?? meta.chapter;
      qc.invalidateQueries({ queryKey: ["chapters", b] });
      qc.invalidateQueries({ queryKey: ["book", b] });
      if (n !== undefined) for (const k of ["chapter", "report", "brief", "versions"])
        qc.invalidateQueries({ queryKey: [k, b, n] });
    };
    const finish = () => { if (key) ss.del(key); stop(); };

    unsubRef.current = subscribeJob(jobId, (ev) => {
      if (ev.type === "started") {
        setStatus("streaming");
        if (ev.chapter !== undefined) setChapter(ev.chapter);
      } else if (ev.type === "token") {
        setStatus("streaming");
        setText((t) => t + ev.text);
      } else if (ev.type === "warning") {
        setWarnings((w) => [...w, ev.message]);
      } else if (ev.type === "artifact") {
        if (ev.brief !== undefined) setBrief(ev.brief);
        refresh(ev.chapter);
      } else if (ev.type === "status") {
        refresh(ev.chapter);
      } else if (ev.type === "done") {
        setStatus("done");
        setElapsedMs(Date.now() - begin);
        refresh(ev.chapter);
        finish();
      } else if (ev.type === "error") {
        setStatus("error");
        setError(ev.error);
        finish();
      } else if (ev.type === "cancelled") {
        setStatus("cancelled");
        finish();
      }
    });
  }, [stop, qc]);

  const start = useCallback((jobId: string, meta: JobMeta = {}) => attach(jobId, meta, false), [attach]);

  /** Re-subscribe to a stored queued/running job for this book+chapter (after reload/navigation). */
  const resume = useCallback(async (bookId: string, chapter?: number) => {
    const key = storeKey(bookId, chapter);
    const raw = ss.get(key);
    if (!raw) return;
    try {
      const m = JSON.parse(raw) as JobMeta & { jobId: string };
      const job = await api.getJob(m.jobId);
      if (job.status === "queued" || job.status === "running") attach(m.jobId, m, true);
      else ss.del(key);
    } catch { ss.del(key); }
  }, [attach]);

  const dismissWarning = useCallback((i: number) => setWarnings((w) => w.filter((_, j) => j !== i)), []);

  const reset = useCallback(() => {
    stop();
    setText("");
    setError(null);
    setStatus("idle");
    setStartedAt(null);
    setElapsedMs(0);
    setWarnings([]);
    setBrief(null);
    setReconnected(false);
  }, [stop]);

  const charCount = text.length;
  const wordCount = text ? (text.trim().split(/\s+/).filter(Boolean).length) : 0;
  const tokensPerSec = elapsedMs > 500 ? (charCount / (elapsedMs / 1000)) : 0;
  const running = status === "starting" || status === "streaming";

  const state: JobStreamState = {
    text, running, status, startedAt, elapsedMs,
    wordCount, charCount, tokensPerSec, error,
    chapter, warnings, brief, reconnected,
  };

  return { state, start, attach, resume, stop, cancel, reset, dismissWarning };
}
