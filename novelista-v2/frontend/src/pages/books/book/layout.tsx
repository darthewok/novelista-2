import { useState } from "react";
import { Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAction } from "@/lib/useAction";
import { ErrorLine } from "@/components/ErrorLine";
import { PhaseStepper, PHASES } from "@/components/PhaseStepper";

export default function BookLayout() {
  const { id } = useParams() as { id: string };
  const { pathname } = useLocation();
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });

  const qc = useQueryClient();
  const act = useAction();
  const [title, setTitle] = useState<string | null>(null); // non-null while renaming

  async function rename() {
    const t = (title ?? "").trim();
    if (!t || t === book?.title) { setTitle(null); return; }
    await act.run(async () => {
      await api.patchBook(id, { title: t });
      await Promise.all([qc.invalidateQueries({ queryKey: ["book", id] }), qc.invalidateQueries({ queryKey: ["books"] })]);
      setTitle(null);
    });
  }

  const active: string = PHASES.find((p) => pathname.includes(`/${p.key}`))?.key ?? "seed";

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between gap-4">
        {title === null ? (
          <h1 className="text-2xl font-semibold truncate cursor-text" title="Click to rename"
              onClick={() => book && setTitle(book.title)}>{book?.title ?? "…"}</h1>
        ) : (
          <input aria-label="Book title" className="input text-2xl font-semibold" autoFocus value={title}
                 onChange={(e) => setTitle(e.target.value)} onBlur={() => setTitle(null)}
                 onKeyDown={(e) => { if (e.key === "Enter") rename(); else if (e.key === "Escape") setTitle(null); }} />
        )}
        <PhaseStepper bookId={id} active={active} />
      </div>
      <ErrorLine error={act.error} />
      <div><Outlet /></div>
    </div>
  );
}
