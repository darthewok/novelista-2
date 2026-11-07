import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";
import { ErrorLine } from "@/components/ErrorLine";
import { useAction } from "@/lib/useAction";

export function VoiceTrials({ bookId }: { bookId: string }) {
  const qc = useQueryClient();
  const { data, refetch } = useQuery({
    queryKey: ["voice-trials", bookId],
    queryFn: () => api.getVoiceTrials(bookId),
    retry: false,
  });
  const trials = useJobStream();
  const pick = useJobStream();
  const act = useAction();

  useEffect(() => { if (trials.state.status === "done") refetch(); }, [trials.state.status]);
  useEffect(() => {
    if (pick.state.status === "done") qc.invalidateQueries({ queryKey: ["artifact", bookId, "voice"] });
  }, [pick.state.status]);

  const text = (trials.state.running ? trials.state.text : data?.text) || "";
  const nums = [...text.matchAll(/^###\s*Trial\s+(\d+)/gm)].map((m) => Number(m[1]));
  const repeated = text.split(/\r?\n/).find((l) => /\(trial \d+ repeated trial \d+ — regenerate\)/.test(l));
  const busy = trials.state.running || pick.state.running;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Voice trials</h2>
          <p className="text-sm text-slate-400">Three opening paragraphs in different registers. Pick one to anchor the voice of the book.</p>
        </div>
        <button className="btn-ghost" disabled={busy || act.busy}
                onClick={() => act.run(async () => trials.start((await api.generateVoiceTrials(bookId)).id))}>
          Generate 3 trial openings
        </button>
      </div>
      <ErrorLine error={act.error} />
      <GenerationProgress state={trials.state} label="Generating trial openings" onCancel={trials.cancel} />
      <GenerationProgress state={pick.state} label="Writing voice document" onCancel={pick.cancel} />
      <div className="card whitespace-pre-wrap font-serif text-sm min-h-[6rem]">
        {text ||
          <span className="text-slate-500">No trials yet.</span>}
      </div>
      {repeated && <p className="text-sm text-amber-400">{repeated.trim()}</p>}
      {text && (
        <div className="flex gap-2">
          {nums.map((n) => (
            <button key={n} className="btn" disabled={busy || act.busy}
                    onClick={() => act.run(async () => pick.start((await api.generateArtifact(bookId, "voice", { choice: n })).id))}>
              Use trial {n}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
