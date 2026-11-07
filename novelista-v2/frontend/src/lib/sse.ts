export type SseEvent =
  | { type: "started"; chapter?: number }
  | { type: "token"; text: string }
  | { type: "artifact"; path: string; chapter?: number; brief?: string }
  | { type: "status"; chapter: number; status: string }
  | { type: "warning"; chapter?: number; message: string }
  | { type: "tighten"; report: unknown }
  | { type: "done"; chapter?: number }
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
