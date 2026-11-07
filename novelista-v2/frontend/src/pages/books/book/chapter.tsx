import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { useAction } from "@/lib/useAction";
import { UnsavedBadge, useEditable, useSaveShortcut, useUnsavedGuard } from "@/lib/useEditable";
import { GenerationProgress } from "@/components/GenerationProgress";
import { ErrorLine } from "@/components/ErrorLine";
import { TellsPanel } from "@/components/TellsPanel";
import { BriefEditor } from "@/components/BriefEditor";

export const STATUS_CHIP: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  drafted: "bg-amber-900/60 text-amber-200",
  polished: "bg-sky-900/60 text-sky-200",
  revising: "bg-fuchsia-900/60 text-fuchsia-200",
  accepted: "bg-emerald-900/60 text-emerald-200",
};

export default function ChapterPage() {
  const { id, n } = useParams() as { id: string; n: string };
  const num = Number(n);
  const qc = useQueryClient();

  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const { data: chapter } = useQuery({
    queryKey: ["chapter", id, num],
    queryFn: () => api.getChapter(id, num),
  });
  const { data: versions } = useQuery({
    queryKey: ["versions", id, num],
    queryFn: () => api.listVersions(id, num),
  });

  const { text, setText, dirty } = useEditable(chapter?.text);
  const [briefDirty, setBriefDirty] = useState(false);
  const [notes, setNotes] = useState("");
  const [polishAfter, setPolishAfter] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [diffVersion, setDiffVersion] = useState<number | null>(null);
  const [priorText, setPriorText] = useState("");
  const [kind, setKind] = useState("Drafting");
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const closeDiffRef = useRef<HTMLButtonElement>(null);

  const { state, start, resume, reset, cancel, dismissWarning } = useJobStream();
  const act = useAction();
  useUnsavedGuard(dirty || briefDirty);

  useEffect(() => { reset(); resume(id, num); }, [id, num]);
  useEffect(() => {
    if (!showDiff) return;
    closeDiffRef.current?.focus();
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") setShowDiff(false); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [showDiff]);

  const busy = state.running || act.busy;
  const waiting = state.status === "starting";
  const meta = { bookId: id, chapter: num };
  const hasText = !!chapter?.text;
  const status = chapter?.status ?? "pending";

  const nums = (book?.chapters ?? []).map((c) => c.number).sort((a, b) => a - b);
  const prev = [...nums].reverse().find((x) => x < num);
  const next = nums.find((x) => x > num);

  const perChapterTarget = (book?.target_words && book?.chapter_count)
    ? Math.round(book.target_words / book.chapter_count)
    : (book?.target_words ?? undefined);

  async function save() {
    await api.putChapter(id, num, text);
    await qc.refetchQueries({ queryKey: ["chapter", id, num] });
    qc.invalidateQueries({ queryKey: ["report", id, num] });
    qc.invalidateQueries({ queryKey: ["chapters", id] });
    qc.invalidateQueries({ queryKey: ["book", id] });
  }
  useSaveShortcut(() => { if (!state.running && dirty) act.run(save); });

  /** Auto-save pending edits, then start a job. */
  function job(label: string, fn: () => Promise<{ id: string }>) {
    return act.run(async () => {
      if (dirty) await save();
      setKind(label);
      start((await fn()).id, { ...meta, kind: label });
    });
  }

  const draft = () => {
    if (hasText && !confirm("Redraft will replace the current text. The current version is kept in Versions. Continue?")) return;
    job("Drafting", () => api.draftChapter(id, num, polishAfter));
  };
  const revise = () => job("Revising", () => api.reviseChapter(id, num, notes, polishAfter));
  const polish = () => job("Polishing", () => api.polishChapter(id, num));
  const editor = () => job("Editor pass on", () => api.editorChapter(id, num));
  const tighten = () => {
    if (!confirm("Tighten removes about 10% of words. A version snapshot is kept. Continue?")) return;
    job("Tightening", () => api.tightenChapter(id, num));
  };
  const fixTells = () => {
    if (!confirm("Rewrites only the sentences flagged as errors. A version snapshot is kept. Continue?")) return;
    job("Fixing tells in", () => api.fixTells(id, num));
  };
  const setAccepted = (accept: boolean) => act.run(async () => {
    if (accept && dirty) await save();
    await (accept ? api.acceptChapter(id, num) : api.unacceptChapter(id, num));
    qc.invalidateQueries({ queryKey: ["chapter", id, num] });
    qc.invalidateQueries({ queryKey: ["chapters", id] });
    qc.invalidateQueries({ queryKey: ["book", id] });
  });

  async function openDiff(v: number) {
    await act.run(async () => {
      const prior = await api.getVersion(id, num, v);
      setPriorText(prior.text);
      setDiffVersion(v);
      setShowDiff(true);
    });
  }

  const priorOnly = versions?.versions.filter((v) => !v.current) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link to={`/books/${id}/chapters`} className="text-slate-500 hover:text-slate-300">← chapters</Link>
            {prev !== undefined && <Link to={`/books/${id}/chapters/${prev}`} className="text-slate-500 hover:text-slate-300">‹ prev</Link>}
            {next !== undefined && <Link to={`/books/${id}/chapters/${next}`} className="text-slate-500 hover:text-slate-300">next ›</Link>}
            <h2 className="text-2xl font-semibold truncate">
              Ch {num}: {chapter?.title ?? "…"}
            </h2>
          </div>
          <p className="text-sm text-slate-400 flex items-center gap-2">
            {chapter?.word_count.toLocaleString()} words · v{chapter?.version} ·
            <span aria-live="polite" className="inline-flex items-center gap-2">
              <span className={`chip ${STATUS_CHIP[status] ?? ""}`}>{status}</span>
              <UnsavedBadge dirty={dirty} />
            </span>
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <button className="btn-ghost" onClick={draft} disabled={busy}>{hasText ? "Redraft" : "Draft"}</button>
          <button className="btn-ghost" onClick={polish} disabled={busy || !hasText}>Polish</button>
          <button className="btn-ghost" onClick={editor} disabled={busy || !hasText}>Editor notes</button>
          <button className="btn-ghost" onClick={tighten} disabled={busy || !hasText}>Tighten</button>
          <button className="btn-ghost" onClick={fixTells} disabled={busy || !hasText}>Fix tells</button>
          {status === "accepted"
            ? <button className="btn-ghost" onClick={() => setAccepted(false)} disabled={busy}>Un-accept</button>
            : <button className="btn-ghost text-emerald-300 border-emerald-900/60" onClick={() => setAccepted(true)}
                      disabled={busy || !hasText}>Accept</button>}
          <button className="btn-ghost" onClick={() => setShowVersions(!showVersions)}>Versions</button>
          <button className="btn" onClick={() => act.run(save)} disabled={busy || !dirty}>Save</button>
        </div>
      </div>
      <ErrorLine error={act.error} />

      {state.warnings.map((w, i) => (
        <div key={i} className="flex items-start justify-between gap-2 rounded border border-amber-700/60 bg-amber-900/30 text-amber-200 text-sm px-3 py-2">
          <span>{w}</span>
          <button onClick={() => dismissWarning(i)} aria-label="Dismiss warning" className="opacity-70 hover:opacity-100">✕</button>
        </div>
      ))}
      {waiting && <p className="text-sm text-slate-400">Waiting for another job…</p>}
      {state.reconnected && <p className="text-xs text-slate-500">Reconnected; earlier output not shown.</p>}

      <GenerationProgress
        state={state}
        label={`${kind} chapter ${num}`}
        targetWords={perChapterTarget}
        onCancel={cancel}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label" htmlFor="chapter-markdown">Chapter markdown</label>
          <textarea id="chapter-markdown" ref={editorRef} className="textarea min-h-[36rem] font-mono text-sm"
                    value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="space-y-4">
          <TellsPanel bookId={id} n={num} editor={editorRef as React.RefObject<HTMLTextAreaElement>} />
          <BriefEditor bookId={id} n={num} onDirty={setBriefDirty} />
          {state.brief && (
            <div className="card">
              <div className="font-semibold mb-1">Latest editor brief</div>
              <div className="whitespace-pre-wrap text-sm text-slate-300">{state.brief}</div>
            </div>
          )}

          <div>
            <label className="label">Stream output</label>
            <div className="card min-h-[10rem] max-h-[16rem] overflow-auto whitespace-pre-wrap font-mono text-sm">
              {state.text || <span className="text-slate-500">Generation output will appear here.</span>}
            </div>
            {state.text && !state.running && (
              <button className="btn-ghost text-sm mt-2" onClick={() => setText(state.text)}>← Use this output</button>
            )}
          </div>

          <div className="card space-y-2">
            <div className="font-semibold">Revise with notes</div>
            <textarea aria-label="Revision notes" className="textarea min-h-[6rem] text-sm" value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="What should change? e.g. 'Cut the opening two paragraphs. Sharpen Mira's dialogue in scene 3.'" />
            <div className="flex items-center gap-4">
              <button className="btn" onClick={revise} disabled={busy || !hasText}>Revise</button>
              <label htmlFor="polish-after" className="text-sm text-slate-300 flex items-center gap-2">
                <input id="polish-after" type="checkbox" checked={polishAfter} onChange={(e) => setPolishAfter(e.target.checked)} />
                polish after
              </label>
            </div>
          </div>

          {showVersions && (
            <div className="card">
              <div className="font-semibold mb-1">Versions</div>
              {priorOnly.length === 0 ? <p className="text-sm text-slate-500">No earlier versions.</p> : (
                <ul className="text-sm space-y-1">
                  {priorOnly.map((v) => (
                    <li key={v.version} className="flex items-center gap-2">
                      <span className="text-slate-500 w-10">v{v.version}</span>
                      <span className="flex-1 text-slate-400">{v.word_count.toLocaleString()} words</span>
                      <button className="btn-ghost text-xs" onClick={() => openDiff(v.version)}>Compare</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {showDiff && (
        <div className="fixed inset-0 bg-slate-950/90 z-20 p-6 overflow-auto"
             role="dialog" aria-modal="true" aria-labelledby="diff-dialog-title">
          <div className="max-w-6xl mx-auto space-y-3">
            <div className="flex items-center justify-between">
              <h3 id="diff-dialog-title" className="text-xl font-semibold">v{diffVersion} ↔ {dirty ? "editor" : "current"}</h3>
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={() => { setText(priorText); setShowDiff(false); }}>
                  Restore this version
                </button>
                <button ref={closeDiffRef} className="btn-ghost" onClick={() => setShowDiff(false)}>Close</button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-slate-500 mb-1">v{diffVersion}</div>
                <pre className="card whitespace-pre-wrap font-mono text-xs max-h-[70vh] overflow-auto">{priorText}</pre>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">{dirty ? "editor (unsaved)" : `current (v${chapter?.version})`}</div>
                <pre className="card whitespace-pre-wrap font-mono text-xs max-h-[70vh] overflow-auto">{text}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
