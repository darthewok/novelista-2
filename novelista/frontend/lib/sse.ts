export type SseEvent =
  | { type: "started" }
  | { type: "token"; text: string }
  | { type: "artifact"; path: string }
  | { type: "done" }
  | { type: "error"; error: string }
  | { type: "cancelled" };

export function subscribeJob(jobId: string, onEvent: (ev: SseEvent) => void): () => void {
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch {}
  };
  es.onerror = () => { es.close(); };
  return () => es.close();
}
