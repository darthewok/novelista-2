"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const statusColor: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  drafted: "bg-amber-900/60 text-amber-200",
  revising: "bg-fuchsia-900/60 text-fuchsia-200",
  accepted: "bg-emerald-900/60 text-emerald-200",
};

export default function ChaptersIndex() {
  const { id } = useParams<{ id: string }>();
  const { data } = useQuery({ queryKey: ["chapters", id], queryFn: () => api.listChapters(id) });

  if (!data) return <div className="text-slate-400">Loading…</div>;
  if (data.length === 0) {
    return (
      <div className="card text-center py-16">
        <p className="text-slate-400">No chapters yet. Generate an outline first.</p>
        <Link href={`/books/${id}/outline`} className="btn mt-4 inline-flex">Go to outline →</Link>
      </div>
    );
  }

  const total = data.reduce((s, c) => s + c.word_count, 0);
  const accepted = data.filter((c) => c.status === "accepted").length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Chapters</h2>
          <p className="text-sm text-slate-400">{accepted} / {data.length} accepted · {total.toLocaleString()} total words</p>
        </div>
      </div>
      <ol className="space-y-2">
        {data.map((c) => (
          <li key={c.number}>
            <Link href={`/books/${id}/chapters/${c.number}`}
                  className="card flex items-center gap-3 hover:border-accent transition-colors">
              <span className="text-slate-500 w-10 text-right font-mono">{c.number}.</span>
              <span className="flex-1 font-medium truncate">{c.title ?? "(untitled)"}</span>
              <span className="text-xs text-slate-400">{c.word_count.toLocaleString()} words</span>
              <span className="text-xs text-slate-500">v{c.version}</span>
              <span className={`chip ${statusColor[c.status] ?? ""}`}>{c.status}</span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
