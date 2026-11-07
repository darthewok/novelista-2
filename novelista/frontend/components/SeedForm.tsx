"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, Book } from "@/lib/api";
import { AUDIENCE_OPTIONS, BOOK_TYPE_OPTIONS, POV_OPTIONS, STYLE_OPTIONS } from "@/lib/catalog";

export function SeedForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [idea, setIdea] = useState("");
  const [audience, setAudience] = useState<string>("");
  const [bookType, setBookType] = useState<string>("");
  const [pov, setPov] = useState<string>("");
  const [style, setStyle] = useState<string>("");
  const [chapterCount, setChapterCount] = useState("");
  const [targetWords, setTargetWords] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedStyle = STYLE_OPTIONS.find((s) => s.value === style);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body = {
        title: title.trim() || "Untitled",
        idea: idea.trim() || null,
        audience: audience || null,
        book_type: bookType || null,
        pov: pov || null,
        writing_style: style || null,
        chapter_count: chapterCount ? Number(chapterCount) : null,
        target_words: targetWords ? Number(targetWords) : null,
      };
      const book = await api.createBook(body as Partial<Book>);
      router.push(`/books/${book.id}/seed`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6 max-w-3xl">
      <div>
        <label className="label" htmlFor="title">Working title</label>
        <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)}
               placeholder="(optional) e.g. The Silent Library" />
      </div>

      <div>
        <label className="label" htmlFor="idea">Your story idea</label>
        <textarea id="idea" className="textarea" value={idea} onChange={(e) => setIdea(e.target.value)}
                  placeholder="Describe your concept in a few sentences. Leave blank and we'll generate 10 candidates for you." />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div>
          <label className="label">Target audience</label>
          <select className="select" value={audience} onChange={(e) => setAudience(e.target.value)}>
            <option value="">No preference</option>
            {AUDIENCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Book type</label>
          <select className="select" value={bookType} onChange={(e) => setBookType(e.target.value)}>
            <option value="">No preference</option>
            {BOOK_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Number of chapters</label>
          <input className="input" type="number" min={1} max={200} value={chapterCount}
                 onChange={(e) => setChapterCount(e.target.value)} placeholder="auto" />
        </div>
        <div>
          <label className="label">Target total words</label>
          <input className="input" type="number" min={500} value={targetWords}
                 onChange={(e) => setTargetWords(e.target.value)} placeholder="auto" />
        </div>
      </div>

      <div>
        <label className="label">Point of view</label>
        <div className="grid gap-2 md:grid-cols-3">
          {POV_OPTIONS.map((o) => (
            <button type="button" key={o.value}
                    onClick={() => setPov(pov === o.value ? "" : o.value)}
                    className={`text-left card hover:border-accent transition-colors ${pov === o.value ? "border-accent ring-1 ring-accent" : ""}`}>
              <div className="font-medium">{o.label}</div>
              <div className="text-xs text-slate-400 mt-1">{o.vibe}</div>
            </button>
          ))}
        </div>
        {pov && (
          <button type="button" onClick={() => setPov("")} className="text-xs text-slate-400 mt-2 underline">clear</button>
        )}
      </div>

      <div>
        <label className="label">Writing style</label>
        <div className="grid gap-2 md:grid-cols-2">
          {STYLE_OPTIONS.map((o) => (
            <button type="button" key={o.value}
                    onClick={() => setStyle(style === o.value ? "" : o.value)}
                    className={`text-left card hover:border-accent transition-colors ${style === o.value ? "border-accent ring-1 ring-accent" : ""}`}>
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-medium">{o.label}</div>
                <div className="text-xs text-slate-500">{o.authors}</div>
              </div>
              <div className="text-xs text-slate-400 mt-1">{o.vibe}</div>
            </button>
          ))}
        </div>
        {selectedStyle && (
          <div className="mt-3 text-xs text-slate-400">
            <span className="chip">selected</span> {selectedStyle.label} — {selectedStyle.authors}
          </div>
        )}
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      <div className="flex gap-3">
        <button className="btn" disabled={submitting} type="submit">
          {submitting ? "Creating…" : "Create book →"}
        </button>
        <button type="button" className="btn-ghost" onClick={() => router.push("/")}>Cancel</button>
      </div>
    </form>
  );
}
