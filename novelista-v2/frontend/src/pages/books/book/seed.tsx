import { useParams } from "react-router-dom";
import { useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";
import { ErrorLine } from "@/components/ErrorLine";
import { useAction } from "@/lib/useAction";
import { UnsavedBadge, useEditable, useSaveShortcut, useUnsavedGuard } from "@/lib/useEditable";

export default function SeedPage() {
  const { id } = useParams() as { id: string };
  const qc = useQueryClient();
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const { data: seed } = useQuery({ queryKey: ["seed", id], queryFn: () => api.getSeed(id) });

  const { text: seedText, setText: setSeedText, dirty } = useEditable(seed?.text);
  const { state, start, cancel } = useJobStream();
  const act = useAction();
  useUnsavedGuard(dirty);

  async function generate() {
    if (dirty) await api.putSeed(id, seedText);
    const job = await api.generateCandidates(id);
    start(job.id);
  }
  async function saveSeed() {
    await api.putSeed(id, seedText);
    await qc.refetchQueries({ queryKey: ["seed", id] });
  }
  const { data: uploads } = useQuery({ queryKey: ["uploads", id], queryFn: () => api.listUploads(id) });
  const fileRef = useRef<HTMLInputElement>(null);
  const upAct = useAction();
  const onFiles = (files: FileList | null) => upAct.run(async () => {
    try { for (const f of Array.from(files ?? [])) await api.uploadFile(id, f); }
    finally { if (fileRef.current) fileRef.current.value = ""; await qc.invalidateQueries({ queryKey: ["uploads", id] }); }
  });
  const removeFile = (name: string) => upAct.run(async () => {
    await api.deleteUpload(id, name);
    await qc.invalidateQueries({ queryKey: ["uploads", id] });
  });
  useSaveShortcut(() => { if (!state.running) act.run(saveSeed); });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Seed — {book?.title ?? "…"}</h2>
          <p className="text-slate-400 mt-1">Lock in the premise before we build the world.</p>
        </div>
        <div className="flex gap-2 items-center">
          <UnsavedBadge dirty={dirty} />
          <button className="btn-ghost" onClick={() => act.run(generate)} disabled={state.running || act.busy}>
            {state.running ? "Generating…" : state.text ? "Regenerate candidates" : "Generate 10 candidates"}
          </button>
          <button className="btn" onClick={() => act.run(saveSeed)} disabled={state.running || act.busy}>Save seed</button>
        </div>
      </div>

      <ErrorLine error={act.error} />
      <GenerationProgress state={state} label="Brainstorming seed candidates" onCancel={cancel} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-2">
          <label className="label" htmlFor="seed-text">Your seed</label>
          <textarea id="seed-text" className="textarea min-h-[28rem] font-mono text-sm"
                    value={seedText} onChange={(e) => setSeedText(e.target.value)}
                    placeholder="Describe the world-differentiator, central tension, cost/constraint, and opening hook." />
          <p className="text-xs text-slate-500">This is what the pipeline will build on. You can edit freely.</p>
        </div>

        <div className="space-y-2">
          <label className="label">Candidates</label>
          <div className="card min-h-[28rem] whitespace-pre-wrap font-mono text-sm overflow-auto max-h-[32rem]">
            {state.text || <span className="text-slate-500">
              Press "Generate 10 candidates" to brainstorm ideas with your local model.
              {book?.idea ? " Your idea will shape the suggestions." : " No starting idea set — the model will propose entirely fresh concepts."}
            </span>}
          </div>
          {state.text && !state.running && (
            <button className="btn-ghost text-sm" onClick={() => setSeedText(state.text)}>← Use candidates as seed</button>
          )}
        </div>
      </div>

      <div className="card space-y-3">
        <label className="label" htmlFor="ref-upload">Reference material</label>
        <input id="ref-upload" ref={fileRef} type="file" accept=".md,.txt,.pdf" multiple
               disabled={upAct.busy} onChange={(e) => onFiles(e.target.files)} className="text-sm" />
        <p className="text-xs text-slate-500">Used as background for seed, world, characters and outline generation</p>
        {upAct.busy && <p className="text-sm text-slate-400">Working…</p>}
        <ErrorLine error={upAct.error} />
        {uploads?.files.length ? (
          <ul className="space-y-1 text-sm">
            {uploads.files.map((f) => (
              <li key={f.name} className="flex items-center justify-between gap-2">
                <span>{f.name} <span className="text-slate-500">({(f.size / 1024).toFixed(1)} KB)</span></span>
                <button className="btn-ghost text-sm" disabled={upAct.busy} onClick={() => removeFile(f.name)}>Delete</button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
