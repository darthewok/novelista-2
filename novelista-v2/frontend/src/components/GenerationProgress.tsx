import type { JobStreamState } from "@/lib/useJobStream";

type Props = {
  state: JobStreamState;
  label: string;            // e.g. "Generating world", "Drafting chapter 3"
  targetWords?: number | null;
  onCancel?: () => void;
};

function formatElapsed(ms: number) {
  const s = Math.floor(ms / 1000);
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}

export function GenerationProgress({ state, label, targetWords, onCancel }: Props) {
  const { status, running, elapsedMs, wordCount, tokensPerSec } = state;

  if (status === "idle") return null;

  const pct = targetWords && wordCount > 0 ? Math.min(100, (wordCount / targetWords) * 100) : null;
  const rate = tokensPerSec > 0 ? `${tokensPerSec.toFixed(0)} chars/s` : "warming up…";

  const statusLabel =
    status === "starting" ? "starting" :
    status === "streaming" ? (wordCount === 0 ? "thinking" : "streaming") :
    status;

  const statusColor =
    status === "error" ? "text-red-400" :
    status === "done" ? "text-emerald-400" :
    status === "cancelled" ? "text-slate-400" :
    "text-accent";

  return (
    <div className="card space-y-3" role="status" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {running && (
            <span className="relative flex h-3 w-3 shrink-0" aria-hidden>
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-accent" />
            </span>
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{label}</div>
            <div className="text-xs text-slate-500">
              <span className={statusColor}>{statusLabel}</span>
              <span className="mx-2 text-slate-700">·</span>
              {formatElapsed(elapsedMs)} elapsed
              <span className="mx-2 text-slate-700">·</span>
              {wordCount.toLocaleString()} words
              {targetWords ? <> <span className="text-slate-600">/ {targetWords.toLocaleString()}</span></> : null}
              {running && wordCount > 0 && (
                <>
                  <span className="mx-2 text-slate-700">·</span>
                  {rate}
                </>
              )}
            </div>
          </div>
        </div>
        {running && onCancel && (
          <button type="button" onClick={onCancel}
                  className="btn-ghost text-xs border-red-900/60 text-red-300">
            Cancel
          </button>
        )}
      </div>

      {pct !== null ? (
        <div className="h-1.5 bg-slate-800 rounded overflow-hidden" role="progressbar" aria-label="progress"
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div className="h-full bg-accent transition-all duration-200"
               style={{ width: `${pct}%` }} />
        </div>
      ) : running ? (
        <div className="h-1.5 bg-slate-800 rounded overflow-hidden relative" role="progressbar" aria-label="progress"
             aria-busy="true">
          <div className="absolute inset-y-0 w-1/3 bg-accent/70 animate-pulse rounded"
               style={{ animation: "novelistaSlide 1.8s ease-in-out infinite" }} />
        </div>
      ) : null}

      {running && wordCount === 0 && elapsedMs > 5000 && (
        <div className="text-xs text-slate-500">
          Local models can take 15–60 seconds to produce the first token on large prompts.
          Everything is fine — we'll keep waiting.
        </div>
      )}

      {status === "error" && state.error && (
        <div className="text-xs text-red-400">{state.error}</div>
      )}

    </div>
  );
}
