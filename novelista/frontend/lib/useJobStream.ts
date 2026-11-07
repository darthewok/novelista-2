"use client";
import { useCallback, useEffect, useRef, useState } from "react";
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

  const start = useCallback((jobId: string) => {
    jobIdRef.current = jobId;
    setText("");
    setError(null);
    setStatus("starting");
    const begin = Date.now();
    setStartedAt(begin);
    setElapsedMs(0);

    unsubRef.current = subscribeJob(jobId, (ev) => {
      if (ev.type === "started") {
        setStatus("streaming");
      } else if (ev.type === "token") {
        setStatus("streaming");
        setText((t) => t + ev.text);
      } else if (ev.type === "done") {
        setStatus("done");
        setElapsedMs(Date.now() - begin);
        stop();
      } else if (ev.type === "error") {
        setStatus("error");
        setError(ev.error);
        stop();
      } else if (ev.type === "cancelled") {
        setStatus("cancelled");
        stop();
      }
    });
  }, [stop]);

  const reset = useCallback(() => {
    stop();
    setText("");
    setError(null);
    setStatus("idle");
    setStartedAt(null);
    setElapsedMs(0);
  }, [stop]);

  const charCount = text.length;
  const wordCount = text ? (text.trim().split(/\s+/).filter(Boolean).length) : 0;
  const tokensPerSec = elapsedMs > 500 ? (charCount / (elapsedMs / 1000)) : 0;
  const running = status === "starting" || status === "streaming";

  const state: JobStreamState = {
    text, running, status, startedAt, elapsedMs,
    wordCount, charCount, tokensPerSec, error,
  };

  return { state, start, stop, cancel, reset };
}
