import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const RING = ["ring-2", "ring-amber-400"];

export function TellsPanel({ bookId, n, editor }: { bookId: string; n: number; editor: React.RefObject<HTMLTextAreaElement> }) {
  const [open, setOpen] = useState(true);
  const { data } = useQuery({ queryKey: ["report", bookId, n], queryFn: () => api.getReport(bookId, n), retry: false });

  function jump(line: number) {
    const ta = editor.current;
    if (!ta) return;
    const lines = ta.value.split("\n");
    const idx = Math.min(Math.max(line, 1), lines.length) - 1;
    const start = lines.slice(0, idx).reduce((s, l) => s + l.length + 1, 0);
    ta.focus();
    ta.setSelectionRange(start, start + lines[idx].length);
    const lh = parseFloat(getComputedStyle(ta).lineHeight) || 20;
    ta.scrollTop = Math.max(0, idx * lh - ta.clientHeight / 3);
    ta.classList.add(...RING);
    window.setTimeout(() => ta.classList.remove(...RING), 1000);
  }

  const m = data?.metrics?.word_count !== undefined ? data.metrics : undefined;  // {} until first scan
  const groups = new Map<string, NonNullable<typeof data>["findings"]>();
  data?.findings.forEach((f) => groups.set(f.rule, [...(groups.get(f.rule) ?? []), f]));

  return (
    <div className="card space-y-2" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button className="w-full text-left font-semibold flex justify-between" onClick={() => setOpen(!open)}
              aria-expanded={open}>
        <span>
          {data
            ? `Tells: ${data.error_count} errors, ${data.warning_count} warnings · tells/1000 words: ${m?.tells_per_1000?.toFixed(1) ?? "–"}`
            : "Tells: not scanned yet"}
        </span>
        <span className="text-slate-500">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <>
          {m && (
            <div className="text-xs text-slate-400 flex gap-4 flex-wrap">
              <span>{m.word_count.toLocaleString()} words</span>
              <span>sentence CV {m.sentence_len_cv.toFixed(2)}</span>
              <span>em-dash/150 {m.em_dash_per_150.toFixed(1)}</span>
              <span>adverb tags {(m.adverb_tag_ratio * 100).toFixed(0)}%</span>
            </div>
          )}
          {!data ? <p className="text-sm text-slate-500">Not scanned yet.</p>
            : data.findings.length === 0 ? <p className="text-sm text-slate-500">No tells found.</p>
            : (
              <div className="space-y-3 max-h-80 overflow-auto">
                {[...groups].map(([rule, fs]) => (
                  <div key={rule}>
                    <div className="text-xs font-mono text-slate-300">{rule} ({fs.length})</div>
                    <ul className="space-y-1">
                      {fs.map((f, i) => (
                        <li key={i}>
                          <button className={`text-left text-sm w-full hover:bg-slate-800 rounded px-1 ${f.severity === "error" ? "text-red-400" : "text-amber-300"}`}
                                  onClick={() => jump(f.line)}>
                            <span className="font-mono text-xs mr-2">L{f.line}</span>
                            “{f.quote}” <span className="text-slate-400">— {f.message}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
        </>
      )}
    </div>
  );
}
