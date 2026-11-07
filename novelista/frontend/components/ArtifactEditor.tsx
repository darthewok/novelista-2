"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";

type Kind = "world" | "characters" | "voice" | "canon";
const GENERATABLE: Record<Kind, boolean> = { world: true, characters: true, voice: false, canon: false };

const LABEL: Record<Kind, string> = {
  world: "Generating world document",
  characters: "Generating character registry",
  voice: "",
  canon: "",
};

export function ArtifactEditor({ bookId, kind, title, hint }:
    { bookId: string; kind: Kind; title: string; hint?: string }) {
  const qc = useQueryClient();
  const { data, refetch } = useQuery({
    queryKey: ["artifact", bookId, kind],
    queryFn: () => api.getArtifact(bookId, kind),
  });
  const [text, setText] = useState("");
  const { state, start, cancel } = useJobStream();

  useEffect(() => { if (data?.text !== undefined) setText(data.text); }, [data?.text]);

  // When the job finishes successfully, pull the persisted artifact from the server.
  useEffect(() => { if (state.status === "done") refetch(); }, [state.status]);

  async function generate() {
    if (!GENERATABLE[kind]) return;
    const job = await api.generateArtifact(bookId, kind as "world" | "characters");
    start(job.id);
  }

  async function save() {
    await api.putArtifact(bookId, kind, text);
    qc.invalidateQueries({ queryKey: ["artifact", bookId, kind] });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{title}</h2>
          {hint && <p className="text-sm text-slate-400">{hint}</p>}
        </div>
        <div className="flex gap-2">
          {GENERATABLE[kind] && (
            <button className="btn-ghost" onClick={generate} disabled={state.running}>
              {state.running ? "Generating…" : (data?.text ? "Regenerate" : "Generate")}
            </button>
          )}
          <button className="btn" onClick={save} disabled={state.running}>Save</button>
        </div>
      </div>

      <GenerationProgress state={state} label={LABEL[kind]} onCancel={cancel} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label">Editor</label>
          <textarea className="textarea min-h-[32rem] font-mono text-sm" value={text}
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
