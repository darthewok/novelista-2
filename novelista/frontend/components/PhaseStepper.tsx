"use client";
import Link from "next/link";

const PHASES = [
  { key: "seed",       label: "Seed" },
  { key: "world",      label: "World" },
  { key: "characters", label: "Characters" },
  { key: "outline",    label: "Outline" },
  { key: "chapters",   label: "Chapters" },
  { key: "export",     label: "Export" },
] as const;

export function PhaseStepper({ bookId, active }: { bookId: string; active: string }) {
  return (
    <nav className="flex flex-wrap gap-1 text-sm">
      {PHASES.map((p, i) => {
        const isActive = p.key === active;
        return (
          <Link key={p.key} href={`/books/${bookId}/${p.key}`}
                className={`px-3 py-1.5 rounded border transition-colors ${
                  isActive
                    ? "bg-accent border-accent text-white"
                    : "border-slate-700 hover:bg-slate-800 text-slate-300"
                }`}>
            <span className="text-slate-500 mr-1">{i + 1}.</span>{p.label}
          </Link>
        );
      })}
    </nav>
  );
}
