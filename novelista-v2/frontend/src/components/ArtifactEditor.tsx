import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ArtifactKind } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";
import { ErrorLine } from "@/components/ErrorLine";
import { useAction } from "@/lib/useAction";
import { UnsavedBadge, useEditable, useSaveShortcut, useUnsavedGuard } from "@/lib/useEditable";

type Kind = ArtifactKind;

const LABEL: Record<Kind, string> = {
  world: "Generating world document",
  characters: "Generating character registry",
  voice: "Generating voice document",
  canon: "Generating canon",
};

export function ArtifactEditor({ bookId, kind, title, hint }:
    { bookId: string; kind: Kind; title: string; hint?: string }) {
  const qc = useQueryClient();
  const { data, refetch } = useQuery({
    queryKey: ["artifact", bookId, kind],
    queryFn: () => api.getArtifact(bookId, kind),
  });
  const { text, setText, dirty } = useEditable(data?.text);
  const { state, start, cancel } = useJobStream();
  const act = useAction();
  useUnsavedGuard(dirty);

  // When the job finishes successfully, pull the persisted artifact from the server.
  useEffect(() => { if (state.status === "done") refetch(); }, [state.status]);

  async function generate() {
    if (data?.text && !confirm("Regenerate will replace this document (a .prev.md copy is kept). Continue?")) return;
    if (dirty) await api.putArtifact(bookId, kind, text);
    const job = await api.generateArtifact(bookId, kind, kind === "voice" ? { choice: null } : undefined);
    start(job.id);
  }

  async function save() {
    await api.putArtifact(bookId, kind, text);
    await qc.refetchQueries({ queryKey: ["artifact", bookId, kind] });
  }
  useSaveShortcut(() => { if (!state.running) act.run(save); });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{title}</h2>
          {hint && <p className="text-sm text-slate-400">{hint}</p>}
        </div>
        <div className="flex gap-2 items-center">
          <button className="btn-ghost" onClick={() => act.run(generate)} disabled={state.running || act.busy}>
            {state.running ? "Generating…" : (data?.text ? "Regenerate" : "Generate")}
          </button>
          <UnsavedBadge dirty={dirty} />
          <button className="btn" onClick={() => act.run(save)} disabled={state.running || act.busy}>Save</button>
        </div>
      </div>
      <ErrorLine error={act.error} />

      <GenerationProgress state={state} label={LABEL[kind]} onCancel={cancel} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label" htmlFor="artifact-editor">Editor</label>
          <textarea id="artifact-editor" className="textarea min-h-[32rem] font-mono text-sm" value={text}
                    onChange={(e) => setText(e.target.value)} />
        </div>
        <div>
          <label className="label">Stream output</label>
          <div className="card min-h-[32rem] max-h-[36rem] overflow-auto whitespace-pre-wrap font-mono text-sm">
            {state.text || <span className="text-slate-500">Generation output will appear here.</span>}
          </div>
          {state.text && !state.running && (
            <button className="btn-ghost text-sm mt-2" onClick={() => setText(state.text)}>
              ← Use this output in the editor
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
