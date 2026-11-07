import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";
import { ErrorLine } from "@/components/ErrorLine";
import { useAction } from "@/lib/useAction";
import { UnsavedBadge, useEditable, useSaveShortcut, useUnsavedGuard } from "@/lib/useEditable";

export default function OutlinePage() {
  const { id } = useParams() as { id: string };
  const qc = useQueryClient();
  const { data, refetch } = useQuery({ queryKey: ["outline", id], queryFn: () => api.getOutline(id) });
  const { text, setText, dirty } = useEditable(data?.text);
  const { state, start, cancel } = useJobStream();
  const act = useAction();
  useUnsavedGuard(dirty);

  useEffect(() => {
    if (state.status === "done") {
      refetch();
      qc.invalidateQueries({ queryKey: ["book", id] });
      qc.invalidateQueries({ queryKey: ["chapters", id] });
    }
  }, [state.status]);

  async function generate() {
    if (data?.text && !confirm("Regenerate will replace this document (a .prev.md copy is kept). Continue?")) return;
    if (dirty) await api.putOutline(id, text);
    const job = await api.generateOutline(id);
    start(job.id);
  }

  async function save() {
    const r = await api.putOutline(id, text);
    await qc.refetchQueries({ queryKey: ["outline", id] });
    qc.invalidateQueries({ queryKey: ["book", id] });
    qc.invalidateQueries({ queryKey: ["chapters", id] });
    alert(`Saved. ${r.chapter_count} chapter${r.chapter_count === 1 ? "" : "s"} detected.`);
  }
  useSaveShortcut(() => { if (!state.running) act.run(save); });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Outline</h2>
          <p className="text-sm text-slate-400">Chapter headings use <code>### Ch N: Title</code>. Chapter rows are synced on save.</p>
        </div>
        <div className="flex gap-2 items-center">
          <button className="btn-ghost" onClick={() => act.run(generate)} disabled={state.running || act.busy}>
            {state.running ? "Generating…" : (data?.text ? "Regenerate" : "Generate")}
          </button>
          <UnsavedBadge dirty={dirty} />
          <button className="btn" onClick={() => act.run(save)} disabled={state.running || act.busy}>Save & sync chapters</button>
        </div>
      </div>
      <ErrorLine error={act.error} />

      <GenerationProgress state={state} label="Generating outline" onCancel={cancel} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label" htmlFor="outline-markdown">Outline markdown</label>
          <textarea id="outline-markdown" className="textarea min-h-[32rem] font-mono text-sm"
                    value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div>
          <label className="label">Stream output</label>
          <div className="card min-h-[32rem] max-h-[36rem] overflow-auto whitespace-pre-wrap font-mono text-sm">
            {state.text || <span className="text-slate-500">Generation output will appear here.</span>}
          </div>
          {state.text && !state.running && (
            <button className="btn-ghost text-sm mt-2" onClick={() => setText(state.text)}>← Use this outline</button>
          )}
        </div>
      </div>

      {data && data.chapters.length > 0 && (
        <div className="card">
          <div className="font-semibold mb-2">Detected chapters</div>
          <ol className="space-y-1 text-sm">
            {data.chapters.map((c) => (
              <li key={c.number} className="flex gap-2">
                <span className="text-slate-500 w-8">{c.number}.</span>
                <span className="flex-1">{c.title ?? "(untitled)"}</span>
                <span className="chip">{c.status}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
