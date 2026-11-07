"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import { GenerationProgress } from "@/components/GenerationProgress";

export default function ChapterPage() {
  const { id, n } = useParams<{ id: string; n: string }>();
  const num = Number(n);
  const qc = useQueryClient();

  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const { data: chapter } = useQuery({
    queryKey: ["chapter", id, num],
    queryFn: () => api.getChapter(id, num),
  });
  const { data: evalData, refetch: refetchEval } = useQuery({
    queryKey: ["eval", id, num],
    queryFn: () => api.evaluateChapter(id, num),
  });
  const { data: versions, refetch: refetchVersions } = useQuery({
    queryKey: ["versions", id, num],
    queryFn: () => api.listVersions(id, num),
  });

  const [text, setText] = useState("");
  const [notes, setNotes] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [diffVersion, setDiffVersion] = useState<number | null>(null);
  const [priorText, setPriorText] = useState("");
  const [kind, setKind] = useState<"draft" | "revise">("draft");

  const { state, start, cancel } = useJobStream();

  useEffect(() => { if (chapter?.text !== undefined) setText(chapter.text); }, [chapter?.text]);
  useEffect(() => {
    if (state.status === "done") {
      qc.invalidateQueries({ queryKey: ["chapter", id, num] });
      refetchEval(); refetchVersions();
    }
  }, [state.status]);

  const perChapterTarget = (book?.target_words && book?.chapter_count)
    ? Math.round(book.target_words / book.chapter_count)
    : (book?.target_words ?? undefined);

  async function startDraft() {
    setKind("draft");
    const job = await api.draftChapter(id, num);
    start(job.id);
  }
  async function startRevise() {
    setKind("revise");
    const job = await api.reviseChapter(id, num, notes);
    start(job.id);
  }

  async function save() {
    await api.putChapter(id, num, text);
    qc.invalidateQueries({ queryKey: ["chapter", id, num] });
    refetchEval();
  }

  async function accept() {
    await api.acceptChapter(id, num);
    qc.invalidateQueries({ queryKey: ["chapter", id, num] });
  }

  async function openDiff(v: number) {
    const prior = await api.getVersion(id, num, v);
    setPriorText(prior.text);
    setDiffVersion(v);
    setShowDiff(true);
  }

  const totalVersions = versions?.versions.length ?? 0;
  const priorOnly = versions?.versions.filter((v) => !v.current) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link href={`/books/${id}/chapters`} className="text-slate-500 hover:text-slate-300">← chapters</Link>
            <h2 className="text-2xl font-semibold truncate">
              Ch {num}: {chapter?.title ?? "…"}
            </h2>
          </div>
          <p className="text-sm text-slate-400">
            {chapter?.word_count.toLocaleString()} words · v{chapter?.version} · <span className="chip">{chapter?.status}</span>
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn-ghost" onClick={startDraft} disabled={state.running}>
            {chapter?.text ? "Redraft" : "Draft"}
          </button>
          <button className="btn" onClick={save} disabled={state.running}>Save</button>
          <button className="btn-ghost text-emerald-300 border-emerald-900/60" onClick={accept}
                  disabled={state.running || chapter?.status === "accepted"}>Accept</button>
        </div>
      </div>

      <GenerationProgress
        state={state}
        label={kind === "revise" ? `Revising chapter ${num}` : `Drafting chapter ${num}`}
        targetWords={perChapterTarget}
        onCancel={cancel}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label">Chapter markdown</label>
          <textarea className="textarea min-h-[36rem] font-mono text-sm"
                    value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="space-y-4">
          <div>
            <label className="label">Stream output</label>
            <div className="card min-h-[18rem] max-h-[22rem] overflow-auto whitespace-pre-wrap font-mono text-sm">
              {state.text || <span className="text-slate-500">Generation output will appear here.</span>}
            </div>
            {state.text && !state.running && (
              <button className="btn-ghost text-sm mt-2" onClick={() => setText(state.text)}>← Use this output</button>
            )}
          </div>

          <div className="card space-y-2">
            <div className="font-semibold">Revise with notes</div>
            <textarea className="textarea min-h-[6rem] text-sm" value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="What should change? e.g. 'Cut the opening two paragraphs. Sharpen Mira's dialogue in scene 3.'" />
            <button className="btn" onClick={startRevise}
                    disabled={state.running || !chapter?.text}>Revise</button>
          </div>

          <div className="card">
            <div className="font-semibold mb-1">Evaluation</div>
            {!evalData || evalData.warnings.length === 0 ? (
              <p className="text-sm text-slate-500">No warnings.</p>
            ) : (
              <ul className="text-sm space-y-1">
                {evalData.warnings.map((w, i) => (
                  <li key={i} className={w.severity === "error" ? "text-red-400" : "text-amber-300"}>
                    <span className="font-mono text-xs mr-2">[{w.severity}]</span>{w.message}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {totalVersions > 1 && (
            <div className="card">
              <div className="font-semibold mb-1">Versions</div>
              <ul className="text-sm space-y-1">
                {priorOnly.map((v) => (
                  <li key={v.version} className="flex items-center gap-2">
                    <span className="text-slate-500 w-10">v{v.version}</span>
                    <span className="flex-1 text-slate-400">{v.word_count.toLocaleString()} words</span>
                    <button className="btn-ghost text-xs" onClick={() => openDiff(v.version)}>Compare</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {showDiff && (
        <div className="fixed inset-0 bg-slate-950/90 z-20 p-6 overflow-auto">
          <div className="max-w-6xl mx-auto space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xl font-semibold">v{diffVersion} ↔ current</h3>
              <button className="btn-ghost" onClick={() => setShowDiff(false)}>Close</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-slate-500 mb-1">v{diffVersion}</div>
                <pre className="card whitespace-pre-wrap font-mono text-xs max-h-[70vh] overflow-auto">{priorText}</pre>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">current (v{chapter?.version})</div>
                <pre className="card whitespace-pre-wrap font-mono text-xs max-h-[70vh] overflow-auto">{text}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
