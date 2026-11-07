"use client";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function ExportPage() {
  const { id } = useParams<{ id: string }>();
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });
  const { data: chapters } = useQuery({ queryKey: ["chapters", id], queryFn: () => api.listChapters(id) });

  const total = chapters?.reduce((s, c) => s + c.word_count, 0) ?? 0;
  const accepted = chapters?.filter((c) => c.status === "accepted").length ?? 0;
  const drafted = chapters?.filter((c) => c.status === "drafted").length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Export</h2>
        <p className="text-sm text-slate-400">Download your manuscript as Markdown or the full zip with every artifact.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card"><div className="text-xs text-slate-500">Chapters</div><div className="text-2xl font-semibold">{chapters?.length ?? 0}</div></div>
        <div className="card"><div className="text-xs text-slate-500">Accepted · drafted</div><div className="text-2xl font-semibold">{accepted} · {drafted}</div></div>
        <div className="card"><div className="text-xs text-slate-500">Words</div><div className="text-2xl font-semibold">{total.toLocaleString()}</div></div>
      </div>

      <div className="flex gap-3">
        <a className="btn" href={api.exportZipUrl(id)} download>Download .zip</a>
        <a className="btn-ghost" href={api.manuscriptUrl(id)} target="_blank" rel="noreferrer">View manuscript.md</a>
        <a className="btn-ghost" href={`${api.manuscriptUrl(id)}?accepted_only=true`} target="_blank" rel="noreferrer">View accepted-only manuscript</a>
      </div>

      <div className="card text-sm text-slate-400">
        The zip contains: <code>manuscript.md</code>, per-chapter <code>chapters/ch_NN.md</code>,
        and <code>seed.txt</code> / <code>world.md</code> / <code>characters.md</code> /
        <code>outline.md</code> / <code>voice.md</code> / <code>canon.md</code> when present.
        Revision snapshots (<code>ch_NN.v*.md</code>) are excluded from the zip — they stay in the book's directory.
      </div>
    </div>
  );
}
