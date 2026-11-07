import { Link } from "react-router-dom";
import { Book } from "@/lib/api";

const statusColor: Record<string, string> = {
  draft: "bg-slate-700 text-slate-200",
  foundation: "bg-indigo-900/60 text-indigo-200",
  drafting: "bg-amber-900/60 text-amber-200",
  revising: "bg-fuchsia-900/60 text-fuchsia-200",
  complete: "bg-emerald-900/60 text-emerald-200",
};

function derive(b: Book): string {
  const c = b.chapters;
  if (c.length && c.every((x) => x.status === "accepted")) return "complete";
  if (c.some((x) => x.word_count > 0)) return "drafting";
  return c.length ? "foundation" : "draft";
}

export function BookCard({ book, onDelete }: { book: Book; onDelete: (id: string) => void }) {
  const status = derive(book);
  const wordCount = book.chapters.reduce((s, c) => s + c.word_count, 0);
  return (
    <div className="card flex flex-col gap-3 hover:border-accent transition-colors">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/books/${book.id}/seed`} className="font-semibold text-lg hover:text-accent line-clamp-2">
          {book.title}
        </Link>
        <span className={`chip ${statusColor[status] ?? ""}`}>{status}</span>
      </div>
      {book.idea && <p className="text-sm text-slate-400 line-clamp-3">{book.idea}</p>}
      <div className="flex items-center justify-between text-xs text-slate-500 mt-auto">
        <span>{book.chapters.length} ch · {wordCount.toLocaleString()} words</span>
        <span>{new Date(book.updated_at).toLocaleDateString()}</span>
      </div>
      <div className="flex gap-2">
        <Link to={`/books/${book.id}/seed`} className="btn-ghost text-sm flex-1 justify-center">Open</Link>
        <button className="btn-ghost text-sm text-red-400 border-red-900/50"
                onClick={() => onDelete(book.id)}>Delete</button>
      </div>
    </div>
  );
}
