"use client";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { BookCard } from "@/components/BookCard";

export default function Dashboard() {
  const qc = useQueryClient();
  const { data: books, isLoading, error } = useQuery({ queryKey: ["books"], queryFn: api.listBooks });

  async function handleDelete(id: string) {
    if (!confirm("Delete this book and its artifacts? This cannot be undone.")) return;
    await api.deleteBook(id);
    qc.invalidateQueries({ queryKey: ["books"] });
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your books</h1>
          <p className="text-slate-400 mt-1">Every project, at a glance.</p>
        </div>
        <Link href="/books/new" className="btn">+ New book</Link>
      </div>

      {isLoading && <div className="text-slate-400">Loading…</div>}
      {error && <div className="text-red-400">{(error as Error).message}</div>}
      {books && books.length === 0 && (
        <div className="card text-center py-16">
          <p className="text-slate-400">No books yet.</p>
          <Link href="/books/new" className="btn mt-4 inline-flex">Start your first book →</Link>
        </div>
      )}
      {books && books.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {books.map((b) => <BookCard key={b.id} book={b} onDelete={handleDelete} />)}
        </div>
      )}
    </div>
  );
}
