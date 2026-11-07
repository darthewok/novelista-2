import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ErrorLine } from "@/components/ErrorLine";
import { useAction } from "@/lib/useAction";
import { UnsavedBadge, useEditable, useSaveShortcut } from "@/lib/useEditable";

export function BriefEditor({ bookId, n, onDirty }: { bookId: string; n: number; onDirty?: (d: boolean) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["brief", bookId, n], queryFn: () => api.getBrief(bookId, n) });
  const { text, setText, dirty } = useEditable(data?.text);
  const act = useAction();
  useEffect(() => { onDirty?.(dirty); }, [dirty]);

  async function save() {
    await api.putBrief(bookId, n, text);
    await qc.refetchQueries({ queryKey: ["brief", bookId, n] });
  }
  useSaveShortcut(() => { if (open && dirty) act.run(save); });

  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between">
        <button className="font-semibold" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "−" : "+"} Revision brief
        </button>
        <div className="flex items-center gap-2">
          <UnsavedBadge dirty={dirty} />
          {open && <button className="btn text-sm" onClick={() => act.run(save)} disabled={act.busy}>Save</button>}
        </div>
      </div>
      {open && (
        <>
          <textarea aria-label="Revision brief" className="textarea min-h-[8rem] text-sm font-mono" value={text} onChange={(e) => setText(e.target.value)} />
          <p className="text-xs text-slate-500">Revise uses this brief automatically.</p>
          <ErrorLine error={act.error} />
        </>
      )}
    </div>
  );
}
