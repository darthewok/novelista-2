import { Link } from "react-router-dom";

export const PHASES = [
  { key: "seed", label: "Seed" },
  { key: "voice", label: "Voice" },
  { key: "world", label: "World" },
  { key: "characters", label: "Characters" },
  { key: "canon", label: "Canon" },
  { key: "outline", label: "Outline" },
  { key: "chapters", label: "Chapters" },
  { key: "export", label: "Export" },
] as const;

export function PhaseStepper({ bookId, active }: { bookId: string; active: string }) {
  return (
    <nav className="flex flex-wrap gap-1 text-sm" aria-label="Phases">
      {PHASES.map((p, i) => {
        const isActive = p.key === active;
        return (
          <Link key={p.key} to={`/books/${bookId}/${p.key}`} aria-current={isActive ? "step" : undefined}
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
