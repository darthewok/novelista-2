import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { useAction } from "@/lib/useAction";
import { ErrorLine } from "@/components/ErrorLine";
import { STATUS_CHIP } from "./chapter";

const qkey = (id: string) => `novelista.draftall.${id}`;
const load = (id: string): string[] => { try { return JSON.parse(sessionStorage.getItem(qkey(id)) ?? "[]"); } catch { return []; } };
const save = (id: string, v: string[]) => { try { sessionStorage.setItem(qkey(id), JSON.stringify(v)); } catch {} };

export default function ChaptersIndex() {
  const { id } = useParams() as { id: string };
  const { data } = useQuery({ queryKey: ["chapters", id], queryFn: () => api.listChapters(id) });
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const [polish, setPolish] = useState(false);
  const act = useAction();
  const { state, attach } = useJobStream();
  const queue = useRef<string[]>([]);

  // Jobs run sequentially server-side; follow them one at a time.
  function next() {
    const jid = queue.current.shift();
    save(id, queue.current);
    if (jid) attach(jid, { bookId: id, kind: "draft" });
  }
  useEffect(() => {
    let live = true;
    (async () => {
      const alive: string[] = [];
      for (const jid of load(id)) {
        try { const j = await api.getJob(jid); if (j.status === "queued" || j.status === "running") alive.push(jid); } catch {}
      }
      if (live && alive.length && !queue.current.length) { queue.current = alive; next(); }
    })();
    return () => { live = false; };
  }, [id]);
  useEffect(() => {
    if (state.status === "done" || state.status === "error" || state.status === "cancelled") next();
  }, [state.status]);

  if (!data) return <div className="text-slate-400">Loading…</div>;
  if (data.length === 0) {
    return (
      <div className="card text-center py-16">
        <p className="text-slate-400">No chapters yet. Generate an outline first.</p>
        <Link to={`/books/${id}/outline`} className="btn mt-4 inline-flex">Go to outline →</Link>
      </div>
    );
  }

  const total = data.reduce((s, c) => s + c.word_count, 0);
  const accepted = data.filter((c) => c.status === "accepted").length;
  const firstPending = data.find((c) => c.status === "pending");
  const perChapter = book?.target_words && book?.chapter_count ? Math.round(book.target_words / book.chapter_count) : null;
  const running = state.running;

  const draftAll = () => act.run(async () => {
    const { job_ids } = await api.draftAll(id, polish);
    queue.current = job_ids;
    save(id, job_ids);
    next();
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold">Chapters</h2>
          <p className="text-sm text-slate-400">{accepted} / {data.length} accepted · {total.toLocaleString()} total words</p>
        </div>
        <div className="flex items-center gap-3">
          {firstPending && (
            <Link to={`/books/${id}/chapters/${firstPending.number}`} className="text-sm text-accent hover:underline">
              Next pending: ch {firstPending.number} →
            </Link>
          )}
          <label htmlFor="polish-each" className="text-sm text-slate-300 flex items-center gap-2">
            <input id="polish-each" type="checkbox" checked={polish} onChange={(e) => setPolish(e.target.checked)} />
            polish each chapter
          </label>
          <button className="btn" onClick={draftAll} disabled={running || act.busy || !firstPending}>Draft all pending</button>
        </div>
      </div>
      <ErrorLine error={act.error} />

      {running && (
        <div className="card text-sm" role="status">
          {state.chapter !== null ? `Drafting chapter ${state.chapter} of ${data.length}` : "Waiting for another job…"}
          {queue.current.length > 0 && <span className="text-slate-500"> · {queue.current.length} more queued</span>}
        </div>
      )}

      <table className="w-full text-sm">
        <thead className="text-left text-slate-500">
          <tr><th className="w-12">#</th><th>Title</th><th>Status</th><th>Words / target</th><th>Tells</th><th>Ver</th></tr>
        </thead>
        <tbody>
          {data.map((c) => (
            <tr key={c.number} className="border-t border-slate-800 hover:bg-slate-900">
              <td className="py-2 font-mono text-slate-500">{c.number}.</td>
              <td className="font-medium truncate max-w-xs">
                <Link to={`/books/${id}/chapters/${c.number}`} className="hover:text-accent">{c.title ?? "(untitled)"}</Link>
              </td>
              <td><span className={`chip ${STATUS_CHIP[c.status] ?? ""}`}>{c.status}</span></td>
              <td className="text-slate-400">{c.word_count.toLocaleString()}{perChapter ? ` / ${perChapter.toLocaleString()}` : ""}</td>
              <td className={c.tells > 0 ? "text-red-400" : "text-slate-500"}>{c.tells}</td>
              <td className="text-slate-500">v{c.version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
