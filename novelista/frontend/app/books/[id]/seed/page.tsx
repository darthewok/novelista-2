"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";

export default function SeedPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const { data: seed } = useQuery({ queryKey: ["seed", id], queryFn: () => api.getSeed(id) });

  const [seedText, setSeedText] = useState("");
  const { state, start, cancel } = useJobStream();

  useEffect(() => { if (seed?.text && !seedText) setSeedText(seed.text); }, [seed?.text]);

  async function generate() {
    const job = await api.generateCandidates(id);
    start(job.id);
  }
  async function saveSeed() {
    await api.putSeed(id, seedText);
    qc.invalidateQueries({ queryKey: ["seed", id] });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Seed — {book?.title ?? "…"}</h2>
          <p className="text-slate-400 mt-1">Lock in the premise before we build the world.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={generate} disabled={state.running}>
            {state.running ? "Generating…" : state.text ? "Regenerate candidates" : "Generate 10 candidates"}
          </button>
          <button className="btn" onClick={saveSeed} disabled={state.running}>Save seed</button>
        </div>
      </div>

      <GenerationProgress state={state} label="Brainstorming seed candidates" onCancel={cancel} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-2">
          <label className="label">Your seed</label>
          <textarea className="textarea min-h-[28rem] font-mono text-sm"
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
    </div>
  );
}
