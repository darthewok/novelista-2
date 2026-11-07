import { useCallback, useState } from "react";

/** Wraps an async fn: tracks busy + a readable error (api errors are "<status> <message>"). */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); }
    catch (e) { setError((e as Error).message); return undefined; }
    finally { setBusy(false); }
  }, []);
  return { run, busy, error, clear: () => setError(null) };
}
